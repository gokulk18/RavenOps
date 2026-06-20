import json
import asyncio
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
from bson import ObjectId

logger = structlog.get_logger()


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
    log_service_url: str = "http://log-service:8004"
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
mongo_client: Optional[AsyncIOMotorClient] = None
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
        await mq_channel.set_qos(prefetch_count=10)
        # Subscribe to webhook events
        asyncio.create_task(consume_webhook_events())
        logger.info("Connected to RabbitMQ")
    except Exception as e:
        logger.warning("RabbitMQ unavailable", error=str(e))
    logger.info("Workflow service started")
    yield
    if mongo_client:
        mongo_client.close()
    if mq_connection:
        await mq_connection.close()


async def consume_webhook_events():
    try:
        import aio_pika
        exchange = await mq_channel.declare_exchange("workflow-events", aio_pika.ExchangeType.TOPIC, durable=True)
        queue = await mq_channel.declare_queue("workflow-events.workflow-service", durable=True)
        await queue.bind(exchange, routing_key="webhook.received")

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                try:
                    data = json.loads(msg.body.decode())
                    await handle_webhook_event(data)
                except Exception as e:
                    logger.error("Error processing webhook event", error=str(e))

        await queue.consume(on_message)
        logger.info("Subscribed to workflow-events")
    except Exception as e:
        logger.error("Failed to subscribe to events", error=str(e))


async def handle_webhook_event(data: dict):
    payload = data.get("payload", {})
    event_type = data.get("event_type", "")
    repo_id = data.get("repo_id")

    if event_type == "workflow_run":
        run = payload.get("workflow_run", {})
        workflow = payload.get("workflow", {})
        await upsert_workflow_run(run, workflow, repo_id)
    elif event_type == "workflow_job":
        job = payload.get("workflow_job", {})
        await upsert_workflow_job(job, repo_id)


async def upsert_workflow_run(run: dict, workflow: dict, repo_id: Optional[str]):
    now = datetime.now(timezone.utc)

    # Upsert workflow definition
    wf_doc = None
    if workflow.get("id"):
        wf_result = await db.workflow_definitions.find_one_and_update(
            {"github_workflow_id": workflow["id"]},
            {"$set": {
                "github_workflow_id": workflow["id"],
                "repo_id": ObjectId(repo_id) if repo_id else None,
                "name": workflow.get("name", "Unknown"),
                "path": workflow.get("path", ""),
                "state": workflow.get("state", "active"),
                "updated_at": now,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
            return_document=True,
        )
        if wf_result:
            wf_doc = wf_result

    started_at = None
    if run.get("run_started_at"):
        try:
            started_at = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    created_at = None
    if run.get("created_at"):
        try:
            created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    duration = None
    if started_at and run.get("updated_at"):
        try:
            updated = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
            duration = int((updated - started_at).total_seconds())
        except Exception:
            pass

    run_data = {
        "github_run_id": run.get("id"),
        "github_run_number": run.get("run_number"),
        "github_run_attempt": run.get("run_attempt", 1),
        "repo_id": ObjectId(repo_id) if repo_id else None,
        "name": run.get("name", ""),
        "status": run.get("status", "queued"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event", "push"),
        "head_branch": run.get("head_branch", ""),
        "head_sha": run.get("head_sha", ""),
        "head_commit": {
            "message": run.get("head_commit", {}).get("message", ""),
            "author": run.get("head_commit", {}).get("author", {}),
            "timestamp": run.get("head_commit", {}).get("timestamp"),
        },
        "triggering_actor": {
            "github_id": run.get("triggering_actor", {}).get("id"),
            "login": run.get("triggering_actor", {}).get("login", ""),
            "avatar_url": run.get("triggering_actor", {}).get("avatar_url", ""),
        },
        "run_started_at": started_at,
        "updated_at": now,
        "html_url": run.get("html_url", ""),
        "duration_seconds": duration,
        "log_status": "pending",
        "analysis_status": "pending",
        "ai_analysis_id": None,
    }

    if wf_doc:
        run_data["workflow_id"] = wf_doc["_id"]

    await db.workflow_runs.update_one(
        {"github_run_id": run.get("id")},
        {"$set": run_data, "$setOnInsert": {"created_at": created_at or now}},
        upsert=True,
    )

    # Publish completed event if run is done
    if run.get("status") == "completed" and run.get("conclusion") in ["failure", "success", "cancelled"]:
        await publish_event("workflow-events", f"workflow.{run.get('conclusion', 'completed')}", {
            "repo_id": repo_id,
            "run_id": str(run.get("id")),
            "conclusion": run.get("conclusion"),
        })
    elif run.get("status") in ["queued", "in_progress"]:
        await publish_event("workflow-events", "workflow.triggered", {
            "repo_id": repo_id,
            "run_id": str(run.get("id")),
            "status": run.get("status"),
        })


async def upsert_workflow_job(job: dict, repo_id: Optional[str]):
    now = datetime.now(timezone.utc)
    run_doc = await db.workflow_runs.find_one({"github_run_id": job.get("run_id")})
    run_oid = run_doc["_id"] if run_doc else None

    started_at = completed_at = None
    if job.get("started_at"):
        try:
            started_at = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        except Exception:
            pass
    if job.get("completed_at"):
        try:
            completed_at = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
        except Exception:
            pass

    duration = int((completed_at - started_at).total_seconds()) if started_at and completed_at else None

    job_data = {
        "github_job_id": job.get("id"),
        "run_id": run_oid,
        "repo_id": ObjectId(repo_id) if repo_id else None,
        "name": job.get("name", ""),
        "status": job.get("status", "queued"),
        "conclusion": job.get("conclusion"),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_seconds": duration,
        "runner_name": job.get("runner_name", ""),
        "runner_group_name": job.get("runner_group_name", ""),
        "labels": job.get("labels", []),
        "html_url": job.get("html_url", ""),
        "updated_at": now,
    }

    job_result = await db.workflow_jobs.find_one_and_update(
        {"github_job_id": job.get("id")},
        {"$set": job_data, "$setOnInsert": {"created_at": now}},
        upsert=True,
        return_document=True,
    )
    job_db_id = job_result["_id"] if job_result else None

    # Upsert steps
    for step in job.get("steps", []):
        step_started = step_completed = None
        if step.get("started_at"):
            try:
                step_started = datetime.fromisoformat(step["started_at"].replace("Z", "+00:00"))
            except Exception:
                pass
        if step.get("completed_at"):
            try:
                step_completed = datetime.fromisoformat(step["completed_at"].replace("Z", "+00:00"))
            except Exception:
                pass
        step_dur = int((step_completed - step_started).total_seconds()) if step_started and step_completed else None
        await db.workflow_steps.update_one(
            {"job_id": job_db_id, "number": step.get("number")},
            {"$set": {
                "name": step.get("name", ""),
                "number": step.get("number"),
                "status": step.get("status", "queued"),
                "conclusion": step.get("conclusion"),
                "started_at": step_started,
                "completed_at": step_completed,
                "duration_seconds": step_dur,
                "run_id": run_oid,
                "repo_id": ObjectId(repo_id) if repo_id else None,
            }, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )


async def publish_event(topic: str, event: str, payload: dict):
    if not mq_channel:
        return
    try:
        import aio_pika
        exchange = await mq_channel.declare_exchange(topic, aio_pika.ExchangeType.TOPIC, durable=True)
        msg = {
            "event_id": str(ObjectId()), "event": event, "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(), "source_service": "workflow-service",
            "payload": payload,
        }
        await exchange.publish(
            aio_pika.Message(body=json.dumps(msg).encode(), content_type="application/json"),
            routing_key=event,
        )
    except Exception as e:
        logger.error("Publish failed", event_name=event, error=str(e))


app = FastAPI(title="RavenOps Workflow Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "workflow-service", "version": "1.0.0"}


@app.get("/runs")
async def list_runs(
    request: Request,
    repo_id: Optional[str] = None,
    status: Optional[str] = None,
    conclusion: Optional[str] = None,
    branch: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
):
    query: dict = {}
    if repo_id:
        query["repo_id"] = ObjectId(repo_id)
    if status:
        query["status"] = status
    if conclusion:
        query["conclusion"] = conclusion
    if branch:
        query["head_branch"] = branch
    total = await db.workflow_runs.count_documents(query)
    skip = (page - 1) * per_page
    runs = []
    async for r in db.workflow_runs.find(query).skip(skip).limit(per_page).sort("created_at", -1):
        runs.append(_serialize_run(r))
    return {"runs": runs, "total": total, "page": page, "per_page": per_page}


def validate_object_id(id_str: str, name: str = "id"):
    if not ObjectId.is_valid(id_str):
        raise HTTPException(status_code=400, detail=f"Invalid {name} format: {id_str}")


@app.get("/runs/{run_id}")
async def get_run(run_id: str):
    validate_object_id(run_id, "run_id")
    r = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(r)


@app.get("/runs/{run_id}/jobs")
async def get_run_jobs(run_id: str):
    validate_object_id(run_id, "run_id")
    jobs = []
    async for j in db.workflow_jobs.find({"run_id": ObjectId(run_id)}).sort("started_at", 1):
        jobs.append(_serialize_job(j))
    return {"jobs": jobs}


@app.get("/runs/{run_id}/jobs/{job_id}")
async def get_job(run_id: str, job_id: str):
    validate_object_id(run_id, "run_id")
    validate_object_id(job_id, "job_id")
    j = await db.workflow_jobs.find_one({"_id": ObjectId(job_id), "run_id": ObjectId(run_id)})
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialize_job(j)


@app.get("/runs/{run_id}/jobs/{job_id}/steps")
async def get_job_steps(run_id: str, job_id: str):
    validate_object_id(run_id, "run_id")
    validate_object_id(job_id, "job_id")
    steps = []
    async for s in db.workflow_steps.find({"job_id": ObjectId(job_id)}).sort("number", 1):
        steps.append(_serialize_step(s))
    return {"steps": steps}


@app.get("/repos/{repo_id}/runs")
async def repo_runs(repo_id: str, page: int = 1, per_page: int = 20):
    validate_object_id(repo_id, "repo_id")
    query = {"repo_id": ObjectId(repo_id)}
    total = await db.workflow_runs.count_documents(query)
    skip = (page - 1) * per_page
    runs = []
    async for r in db.workflow_runs.find(query).skip(skip).limit(per_page).sort("created_at", -1):
        runs.append(_serialize_run(r))
    return {"runs": runs, "total": total, "page": page, "per_page": per_page}


@app.get("/repos/{repo_id}/stats")
async def repo_stats(repo_id: str):
    validate_object_id(repo_id, "repo_id")
    query = {"repo_id": ObjectId(repo_id)}
    total = await db.workflow_runs.count_documents(query)
    failed = await db.workflow_runs.count_documents({**query, "conclusion": "failure"})
    success = await db.workflow_runs.count_documents({**query, "conclusion": "success"})
    in_progress = await db.workflow_runs.count_documents({**query, "status": "in_progress"})
    success_rate = round((success / total * 100), 1) if total > 0 else 0
    return {
        "total_runs": total, "failed_runs": failed, "successful_runs": success,
        "in_progress": in_progress, "success_rate": success_rate,
        "failure_rate": round(100 - success_rate, 1),
    }


@app.post("/runs/{run_id}/reanalyze")
async def reanalyze(run_id: str, background_tasks: BackgroundTasks):
    validate_object_id(run_id, "run_id")
    r = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Run not found")
    await db.workflow_runs.update_one({"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "pending"}})
    background_tasks.add_task(publish_event, "workflow-events", "workflow.reanalyze",
                              {"run_id": run_id, "repo_id": str(r.get("repo_id", ""))})
    return {"message": "Re-analysis triggered"}


# ── Serializers ───────────────────────────────────────────────────────
def _serialize_run(r: dict) -> dict:
    return {
        "id": str(r["_id"]), "github_run_id": r.get("github_run_id"),
        "github_run_number": r.get("github_run_number"),
        "workflow_id": str(r["workflow_id"]) if r.get("workflow_id") else None,
        "repo_id": str(r["repo_id"]) if r.get("repo_id") else None,
        "name": r.get("name", ""), "status": r.get("status"), "conclusion": r.get("conclusion"),
        "event": r.get("event"), "head_branch": r.get("head_branch"), "head_sha": r.get("head_sha"),
        "head_commit": r.get("head_commit", {}), "triggering_actor": r.get("triggering_actor", {}),
        "run_started_at": r.get("run_started_at"), "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"), "html_url": r.get("html_url"),
        "duration_seconds": r.get("duration_seconds"), "log_status": r.get("log_status", "pending"),
        "analysis_status": r.get("analysis_status", "pending"),
        "ai_analysis_id": str(r["ai_analysis_id"]) if r.get("ai_analysis_id") else None,
    }


def _serialize_job(j: dict) -> dict:
    return {
        "id": str(j["_id"]), "github_job_id": j.get("github_job_id"),
        "run_id": str(j["run_id"]) if j.get("run_id") else None,
        "name": j.get("name"), "status": j.get("status"), "conclusion": j.get("conclusion"),
        "started_at": j.get("started_at"), "completed_at": j.get("completed_at"),
        "duration_seconds": j.get("duration_seconds"), "runner_name": j.get("runner_name"),
        "labels": j.get("labels", []), "html_url": j.get("html_url"),
    }


def _serialize_step(s: dict) -> dict:
    return {
        "id": str(s["_id"]), "name": s.get("name"), "number": s.get("number"),
        "status": s.get("status"), "conclusion": s.get("conclusion"),
        "started_at": s.get("started_at"), "completed_at": s.get("completed_at"),
        "duration_seconds": s.get("duration_seconds"),
    }
