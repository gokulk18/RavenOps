import re
import gzip
import json
import hashlib
import asyncio
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
from bson import ObjectId
from azure.storage.blob import BlobServiceClient

logger = structlog.get_logger()

# ── Error Pattern Library ─────────────────────────────────────────────
PATTERNS = {
    "docker": [
        (re.compile(r"Error response from daemon: (.+)"), "critical"),
        (re.compile(r"failed to solve: (.+)"), "error"),
        (re.compile(r"failed to push .+: (.+)"), "error"),
        (re.compile(r"Cannot connect to the Docker daemon"), "critical"),
        (re.compile(r"Dockerfile: (.+)"), "error"),
    ],
    "terraform": [
        (re.compile(r"│ Error: (.+)"), "critical"),
        (re.compile(r"Error: (.+)"), "error"),
        (re.compile(r"Plan: \d+ to add, \d+ to change, \d+ to destroy"), "info"),
    ],
    "kubernetes": [
        (re.compile(r"Error from server.*: (.+)"), "critical"),
        (re.compile(r"ImagePullBackOff"), "critical"),
        (re.compile(r"CrashLoopBackOff"), "critical"),
        (re.compile(r"OOMKilled"), "critical"),
        (re.compile(r"Evicted"), "error"),
        (re.compile(r"Insufficient (cpu|memory)"), "error"),
    ],
    "python": [
        (re.compile(r"Traceback \(most recent call last\):"), "error"),
        (re.compile(r"([\w]+Error|[\w]+Exception): (.+)"), "error"),
        (re.compile(r"ModuleNotFoundError: (.+)"), "error"),
        (re.compile(r"ImportError: (.+)"), "error"),
        (re.compile(r"SyntaxError: (.+)"), "error"),
        (re.compile(r"AssertionError: (.+)"), "error"),
    ],
    "nodejs": [
        (re.compile(r"npm ERR! (.+)"), "error"),
        (re.compile(r"Cannot find module '(.+)'"), "error"),
        (re.compile(r"UnhandledPromiseRejectionWarning: (.+)"), "error"),
        (re.compile(r"EADDRINUSE|ECONNREFUSED|ENOENT"), "error"),
        (re.compile(r"Error: (.+) at .+:\d+:\d+"), "error"),
    ],
    "java": [
        (re.compile(r"(java\.[\w.]+Exception): (.+)"), "error"),
        (re.compile(r"BUILD FAILURE"), "critical"),
        (re.compile(r"\[ERROR\] (.+)"), "error"),
        (re.compile(r"Tests run: \d+, Failures: (\d+), Errors: (\d+)"), "error"),
        (re.compile(r"java\.lang\.OutOfMemoryError"), "critical"),
    ],
    "golang": [
        (re.compile(r"FAIL\s+(.+)\s+\["), "error"),
        (re.compile(r"panic: (.+)"), "critical"),
        (re.compile(r"undefined: (.+)"), "error"),
        (re.compile(r"cannot use (.+) as (.+)"), "error"),
        (re.compile(r"build failed"), "error"),
    ],
    "test": [
        (re.compile(r"✕ (.+)"), "error"),
        (re.compile(r"FAILED (.+)"), "error"),
        (re.compile(r"● (.+)"), "error"),
        (re.compile(r"Expected: (.+)\s*Received: (.+)"), "error"),
        (re.compile(r"FAILED (.+) - (.+)"), "error"),
        (re.compile(r"AssertionError: (.+)"), "error"),
        (re.compile(r"Tests:.*(\d+) failed"), "error"),
    ],
    "github_actions": [
        (re.compile(r"##\[error\](.+)"), "critical"),
        (re.compile(r"##\[warning\](.+)"), "warning"),
        (re.compile(r"Process completed with exit code (\d+)"), "error"),
        (re.compile(r"Error: The process '(.+)' failed with exit code (\d+)"), "critical"),
    ],
    "network": [
        (re.compile(r"dial tcp .+: i/o timeout"), "error"),
        (re.compile(r"Connection refused"), "error"),
        (re.compile(r"Name or service not known"), "error"),
        (re.compile(r"TLS handshake timeout"), "error"),
        (re.compile(r"connection reset by peer"), "error"),
    ],
    "oom": [
        (re.compile(r"Killed"), "critical"),
        (re.compile(r"Out of memory: Kill process"), "critical"),
        (re.compile(r"MemoryError"), "critical"),
    ],
}

TEST_RESULT_PATTERN = re.compile(
    r"Tests?\s+run:\s*(\d+)[,\s]+Failures:\s*(\d+)[,\s]+Errors:\s*(\d+)|"
    r"(\d+)\s+passed.*?(\d+)\s+failed|"
    r"Tests:\s+(\d+)\s+failed.*?(\d+)\s+passed"
)


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
    azure_storage_connection_string: str = (
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
    )
    azure_blob_container: str = "ravenops-logs"
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
mongo_client = None
db = None
mq_connection = None
mq_channel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db, mq_connection, mq_channel
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_db_name]
    try:
        import aio_pika
        mq_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        mq_channel = await mq_connection.channel()
        asyncio.create_task(consume_log_events())
    except Exception as e:
        logger.warning("RabbitMQ unavailable", error=str(e))
    logger.info("Parser service started")
    yield
    if mongo_client:
        mongo_client.close()
    if mq_connection:
        await mq_connection.close()


async def consume_log_events():
    try:
        import aio_pika
        exchange = await mq_channel.declare_exchange("log-events", aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await mq_channel.declare_queue("log-events.parser-service", durable=True)
        await queue.bind(exchange, routing_key="log.downloaded")

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                payload = data.get("payload", {})
                run_id = payload.get("run_id")
                if run_id:
                    asyncio.create_task(parse_run_logs(run_id))

        await queue.consume(on_message)
    except Exception as e:
        logger.error("Event subscription failed", error=str(e))


def make_fingerprint(message: str) -> str:
    normalized = re.sub(r"[0-9a-f]{8,}", "HASH", message, flags=re.IGNORECASE)
    normalized = re.sub(r"\d+", "N", normalized)
    normalized = normalized.strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()


def parse_log_content(lines: list[str]) -> dict:
    errors = []
    warnings = []
    first_failure = None
    test_results = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "duration_ms": 0}
    in_traceback = False
    traceback_lines = []
    current_step = ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Track step boundaries
        if "##[group]" in line or "##[section]" in line:
            current_step = re.sub(r"##\[(?:group|section)\]", "", line).strip()
        if "##[endgroup]" in line:
            current_step = ""

        # Traceback accumulation
        if "Traceback (most recent call last):" in stripped:
            in_traceback = True
            traceback_lines = [stripped]
            continue
        if in_traceback:
            traceback_lines.append(stripped)
            if stripped and not stripped.startswith(" ") and not stripped.startswith("File ") and len(traceback_lines) > 2:
                in_traceback = False
                err_msg = traceback_lines[-1] if traceback_lines else "Unknown error"
                context = lines[max(0, i - 3): i + 1]
                errors.append({
                    "line_number": i + 1,
                    "severity": "error",
                    "category": "python",
                    "error_type": err_msg.split(":")[0] if ":" in err_msg else "PythonException",
                    "message": err_msg,
                    "raw_line": line,
                    "context_lines": context,
                    "stack_trace": "\n".join(traceback_lines),
                    "fingerprint": make_fingerprint(err_msg),
                })
                if first_failure is None:
                    first_failure = {"line_number": i + 1, "step_name": current_step, "message": err_msg}
                traceback_lines = []
            continue

        # Pattern matching
        for category, pattern_list in PATTERNS.items():
            for pattern, severity in pattern_list:
                match = pattern.search(stripped)
                if match:
                    groups = match.groups()
                    message = groups[0] if groups else stripped
                    context = lines[max(0, i - 2): i + 3]
                    fp = make_fingerprint(message)
                    entry = {
                        "line_number": i + 1,
                        "severity": severity,
                        "category": category,
                        "error_type": pattern.pattern[:40],
                        "message": message[:500],
                        "raw_line": line[:500],
                        "context_lines": context,
                        "stack_trace": None,
                        "fingerprint": fp,
                    }
                    if severity in ("critical", "error"):
                        errors.append(entry)
                        if first_failure is None:
                            first_failure = {"line_number": i + 1, "step_name": current_step, "message": message[:300]}
                    elif severity == "warning":
                        warnings.append(entry)
                    break

        # Test result extraction
        tr_match = TEST_RESULT_PATTERN.search(stripped)
        if tr_match:
            g = tr_match.groups()
            if g[0]:
                test_results["total"] = int(g[0])
                test_results["failed"] = int(g[1]) + int(g[2])
                test_results["passed"] = test_results["total"] - test_results["failed"]
            elif g[3]:
                test_results["passed"] = int(g[3])
                test_results["failed"] = int(g[4])
                test_results["total"] = test_results["passed"] + test_results["failed"]

    all_issues = errors + warnings
    failure_sig = make_fingerprint(" ".join(e["message"] for e in errors[:3])) if errors else "no_errors"

    return {
        "summary": {
            "total_lines": len(lines),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "critical_count": sum(1 for e in errors if e["severity"] == "critical"),
        },
        "errors": all_issues[:200],  # Cap at 200 issues
        "first_failure": first_failure,
        "failure_signature": failure_sig,
        "test_results": test_results,
    }


async def parse_run_logs(run_id: str):
    try:
        run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        if not run:
            logger.warning("Run not found for parsing", run_id=run_id)
            return

        log_meta = await db.logs_metadata.find_one({"run_id": ObjectId(run_id)})
        if not log_meta or log_meta.get("status") != "stored":
            logger.warning("Logs not stored yet", run_id=run_id)
            return

        await db.workflow_runs.update_one({"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "parsing"}})

        # Fetch log from blob
        blob_client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
        container = blob_client.get_blob_client(settings.azure_blob_container, log_meta["blob_path"])
        compressed = container.download_blob().readall()
        content = gzip.decompress(compressed).decode("utf-8", errors="replace")
        lines = content.splitlines()

        parsed = parse_log_content(lines)
        now = datetime.now(timezone.utc)

        # Get job/step info
        job = await db.workflow_jobs.find_one({"run_id": ObjectId(run_id)})
        job_id = job["_id"] if job else None

        doc = {
            "run_id": ObjectId(run_id),
            "repo_id": run.get("repo_id"),
            "job_id": job_id,
            "step_id": None,
            "parsing_version": "1.0.0",
            "parsed_at": now,
            **parsed,
        }

        await db.parsed_logs.update_one(
            {"run_id": ObjectId(run_id)},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

        await db.workflow_runs.update_one(
            {"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "parsed"}}
        )

        # Publish log.parsed event
        if mq_channel:
            import aio_pika
            exchange = await mq_channel.declare_exchange("log-events", aio_pika.ExchangeType.TOPIC, durable=True)
            msg = {
                "event_id": str(ObjectId()), "event": "log.parsed", "version": "1.0",
                "timestamp": now.isoformat(), "source_service": "parser-service",
                "payload": {
                    "run_id": run_id,
                    "error_count": parsed["summary"]["error_count"],
                    "first_failure": parsed["first_failure"],
                },
            }
            await exchange.publish(
                aio_pika.Message(body=json.dumps(msg).encode(), content_type="application/json"),
                routing_key="log.parsed",
            )
        logger.info("Log parsed", run_id=run_id, errors=parsed["summary"]["error_count"])
    except Exception as e:
        logger.error("Parsing failed", run_id=run_id, error=str(e))
        await db.workflow_runs.update_one({"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "failed"}})


app = FastAPI(title="RavenOps Parser Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "parser-service", "version": "1.0.0"}


@app.post("/parse/{run_id}")
async def trigger_parse(run_id: str, background_tasks: BackgroundTasks):
    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    background_tasks.add_task(parse_run_logs, run_id)
    return {"message": "Parsing triggered", "run_id": run_id}


@app.get("/parse/{run_id}/result")
async def get_parse_result(run_id: str):
    result = await db.parsed_logs.find_one({"run_id": ObjectId(run_id)})
    if not result:
        raise HTTPException(status_code=404, detail="Parse result not found")
    return {
        "id": str(result["_id"]), "run_id": run_id,
        "parsed_at": result.get("parsed_at"),
        "parsing_version": result.get("parsing_version"),
        "summary": result.get("summary", {}),
        "errors": result.get("errors", [])[:50],
        "first_failure": result.get("first_failure"),
        "failure_signature": result.get("failure_signature"),
        "test_results": result.get("test_results", {}),
    }
