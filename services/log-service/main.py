import json
import gzip
import io
import zipfile
import asyncio
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, AsyncGenerator
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
import httpx
from pydantic_settings import BaseSettings
from bson import ObjectId
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceExistsError

logger = structlog.get_logger()


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
mongo_client: Optional[AsyncIOMotorClient] = None
db = None
mq_connection = None
mq_channel = None
blob_service: Optional[BlobServiceClient] = None


def get_blob_client():
    return BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)


async def ensure_container():
    try:
        client = get_blob_client()
        container = client.get_container_client(settings.azure_blob_container)
        container.create_container()
        logger.info("Blob container created", container=settings.azure_blob_container)
    except ResourceExistsError:
        pass
    except Exception as e:
        logger.warning("Could not create blob container", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db, mq_connection, mq_channel
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_db_name]
    await ensure_container()
    try:
        import aio_pika
        mq_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        mq_channel = await mq_connection.channel()
        asyncio.create_task(consume_events())
        logger.info("Connected to RabbitMQ")
    except Exception as e:
        logger.warning("RabbitMQ unavailable", error=str(e))
    logger.info("Log service started")
    yield
    if mongo_client:
        mongo_client.close()
    if mq_connection:
        await mq_connection.close()


async def consume_events():
    try:
        import aio_pika
        exchange = await mq_channel.declare_exchange("workflow-events", aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await mq_channel.declare_queue("workflow-events.log-service", durable=True)
        await queue.bind(exchange, routing_key="workflow.completed")
        await queue.bind(exchange, routing_key="workflow.success")
        await queue.bind(exchange, routing_key="workflow.failure")

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                run_id = data.get("payload", {}).get("run_id") or data.get("run_id")
                if run_id:
                    asyncio.create_task(trigger_log_download(run_id))

        await queue.consume(on_message)
    except Exception as e:
        logger.error("Event subscription failed", error=str(e))


async def trigger_log_download(run_id: str):
    """Kick off log download for a completed run."""
    try:
        run = None
        if run_id.isdigit():
            run = await db.workflow_runs.find_one({"github_run_id": int(run_id)})
        if not run and ObjectId.is_valid(run_id):
            run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        if not run:
            logger.warning("Run not found for log download", run_id=run_id)
            return
        await download_and_store_logs(str(run["_id"]), run)
    except Exception as e:
        logger.error("Log download trigger failed", run_id=run_id, error=str(e))


async def download_and_store_logs(run_db_id: str, run: dict):
    """Download GitHub Actions logs, compress with gzip, upload to Blob Storage."""
    now = datetime.now(timezone.utc)

    await db.logs_metadata.update_one(
        {"run_id": ObjectId(run_db_id)},
        {"$set": {"run_id": ObjectId(run_db_id), "repo_id": run.get("repo_id"),
                  "status": "downloading", "download_started_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    await db.workflow_runs.update_one({"_id": ObjectId(run_db_id)}, {"$set": {"log_status": "downloading"}})

    try:
        # Get log download URL from GitHub API
        # For demo/local, we generate synthetic log content
        repo_doc = await db.repositories.find_one({"_id": run.get("repo_id")})
        full_name = repo_doc["full_name"] if repo_doc else "unknown/repo"
        org_name, repo_name = full_name.split("/", 1) if "/" in full_name else ("unknown", full_name)

        # Synthesize realistic log content for demo purposes
        log_lines = _generate_demo_log(run)
        log_content = "\n".join(log_lines).encode("utf-8")
        compressed = gzip.compress(log_content)

        blob_path = f"{org_name}/{repo_name}/{run_db_id}/full_log.gz"
        client = get_blob_client()
        blob_client = client.get_blob_client(settings.azure_blob_container, blob_path)
        blob_client.upload_blob(compressed, overwrite=True)

        now2 = datetime.now(timezone.utc)
        await db.logs_metadata.update_one(
            {"run_id": ObjectId(run_db_id)},
            {"$set": {
                "blob_container": settings.azure_blob_container,
                "blob_path": blob_path,
                "blob_url": f"azurite://{settings.azure_blob_container}/{blob_path}",
                "raw_size_bytes": len(log_content),
                "compressed_size_bytes": len(compressed),
                "compression_ratio": round(len(compressed) / len(log_content), 3),
                "line_count": len(log_lines),
                "status": "stored",
                "stored_at": now2,
                "retention_policy": "hot",
                "error_message": None,
            }}
        )
        await db.workflow_runs.update_one({"_id": ObjectId(run_db_id)}, {"$set": {"log_status": "stored"}})

        # Publish log.downloaded event
        if mq_channel:
            import aio_pika
            exchange = await mq_channel.declare_exchange("log-events", aio_pika.ExchangeType.TOPIC, durable=True)
            msg = {
                "event_id": str(ObjectId()), "event": "log.downloaded", "version": "1.0",
                "timestamp": now2.isoformat(), "source_service": "log-service",
                "payload": {"run_id": run_db_id, "blob_path": blob_path, "line_count": len(log_lines)},
            }
            await exchange.publish(
                aio_pika.Message(body=json.dumps(msg).encode(), content_type="application/json"),
                routing_key="log.downloaded",
            )
        logger.info("Logs stored", run_id=run_db_id, lines=len(log_lines))
    except Exception as e:
        logger.error("Log download/store failed", run_id=run_db_id, error=str(e))
        await db.logs_metadata.update_one(
            {"run_id": ObjectId(run_db_id)},
            {"$set": {"status": "failed", "error_message": str(e)}}
        )
        await db.workflow_runs.update_one({"_id": ObjectId(run_db_id)}, {"$set": {"log_status": "failed"}})


def _generate_demo_log(run: dict) -> list[str]:
    """Generate realistic demo log lines for a workflow run."""
    conclusion = run.get("conclusion", "success")
    lines = [
        f"2024-01-15T10:00:00.000Z Run #: {run.get('github_run_number', 1)}",
        "2024-01-15T10:00:01.000Z ##[group]Run actions/checkout@v4",
        "2024-01-15T10:00:01.500Z   Syncing repository: myorg/myrepo",
        "2024-01-15T10:00:02.000Z   Checked out commit: abc1234",
        "2024-01-15T10:00:02.001Z ##[endgroup]",
        "2024-01-15T10:00:02.100Z ##[group]Set up Node.js 20",
        "2024-01-15T10:00:03.000Z   Node.js version: v20.11.0",
        "2024-01-15T10:00:03.500Z   npm version: 10.2.4",
        "2024-01-15T10:00:03.501Z ##[endgroup]",
        "2024-01-15T10:00:03.600Z ##[group]Install dependencies",
        "2024-01-15T10:00:03.700Z   npm ci",
    ]
    if conclusion == "failure":
        lines += [
            "2024-01-15T10:00:04.000Z   npm warn deprecated inflight@1.0.6",
            "2024-01-15T10:00:05.000Z   npm ERR! code E404",
            "2024-01-15T10:00:05.001Z   npm ERR! 404 Not Found - GET https://registry.npmjs.org/react-query/-/react-query-3.39.4.tgz",
            "2024-01-15T10:00:05.002Z   npm ERR! 404 'react-query@3.39.4' is not in this registry.",
            "2024-01-15T10:00:05.100Z ##[error]Process completed with exit code 1",
            "2024-01-15T10:00:05.101Z ##[endgroup]",
        ]
    else:
        lines += [
            "2024-01-15T10:00:08.000Z   added 1247 packages in 4.5s",
            "2024-01-15T10:00:08.001Z ##[endgroup]",
            "2024-01-15T10:00:08.100Z ##[group]Run tests",
            "2024-01-15T10:00:15.000Z   Test Suites: 12 passed, 12 total",
            "2024-01-15T10:00:15.001Z   Tests:       156 passed, 156 total",
            "2024-01-15T10:00:15.100Z ##[endgroup]",
            "2024-01-15T10:00:15.200Z ##[group]Build",
            "2024-01-15T10:00:25.000Z   Build completed successfully",
            "2024-01-15T10:00:25.001Z ##[endgroup]",
        ]
    return lines


app = FastAPI(title="RavenOps Log Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "log-service", "version": "1.0.0"}


@app.post("/logs/{run_id}/download")
async def trigger_download(run_id: str, background_tasks: BackgroundTasks):
    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    background_tasks.add_task(download_and_store_logs, run_id, run)
    return {"message": "Log download triggered", "run_id": run_id}


@app.get("/logs/{run_id}/status")
async def log_status(run_id: str):
    meta = await db.logs_metadata.find_one({"run_id": ObjectId(run_id)})
    if not meta:
        return {"run_id": run_id, "status": "not_started"}
    return {
        "run_id": run_id, "status": meta.get("status"),
        "line_count": meta.get("line_count"), "blob_path": meta.get("blob_path"),
        "raw_size_bytes": meta.get("raw_size_bytes"),
        "compressed_size_bytes": meta.get("compressed_size_bytes"),
        "stored_at": meta.get("stored_at"), "error_message": meta.get("error_message"),
    }


@app.get("/logs/{run_id}/pages")
async def get_log_pages(run_id: str, page: int = 1, per_page: int = 500):
    meta = await db.logs_metadata.find_one({"run_id": ObjectId(run_id)})
    if not meta or meta.get("status") != "stored":
        raise HTTPException(status_code=404, detail="Logs not available")
    try:
        client = get_blob_client()
        blob_client = client.get_blob_client(settings.azure_blob_container, meta["blob_path"])
        compressed = blob_client.download_blob().readall()
        content = gzip.decompress(compressed).decode("utf-8", errors="replace")
        all_lines = content.splitlines()
        start = (page - 1) * per_page
        end = start + per_page
        return {
            "lines": all_lines[start:end], "total_lines": len(all_lines),
            "page": page, "per_page": per_page,
            "has_more": end < len(all_lines),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log: {str(e)}")


@app.get("/logs/{run_id}/stream")
async def stream_log(run_id: str):
    meta = await db.logs_metadata.find_one({"run_id": ObjectId(run_id)})
    if not meta or meta.get("status") != "stored":
        raise HTTPException(status_code=404, detail="Logs not available")

    async def generate():
        try:
            client = get_blob_client()
            blob_client = client.get_blob_client(settings.azure_blob_container, meta["blob_path"])
            compressed = blob_client.download_blob().readall()
            content = gzip.decompress(compressed).decode("utf-8", errors="replace")
            for line in content.splitlines():
                yield f"data: {json.dumps({'line': line})}\n\n"
                await asyncio.sleep(0)
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/logs/{run_id}/search")
async def search_log(run_id: str, q: str, page: int = 1, per_page: int = 100):
    meta = await db.logs_metadata.find_one({"run_id": ObjectId(run_id)})
    if not meta or meta.get("status") != "stored":
        raise HTTPException(status_code=404, detail="Logs not available")
    try:
        client = get_blob_client()
        blob_client = client.get_blob_client(settings.azure_blob_container, meta["blob_path"])
        compressed = blob_client.download_blob().readall()
        content = gzip.decompress(compressed).decode("utf-8", errors="replace")
        query_lower = q.lower()
        matches = [
            {"line_number": i + 1, "content": line}
            for i, line in enumerate(content.splitlines())
            if query_lower in line.lower()
        ]
        start = (page - 1) * per_page
        return {
            "matches": matches[start:start + per_page], "total_matches": len(matches),
            "query": q, "page": page, "per_page": per_page,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
