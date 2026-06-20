import json
import hashlib
import hmac
import asyncio
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
import httpx
from pydantic_settings import BaseSettings
from bson import ObjectId

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    redis_url: str = "redis://:ravenops_redis@redis:6379/0"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
    service_bus_provider: str = "rabbitmq"
    github_webhook_secret: str = "ravenops-webhook-secret-local"
    github_app_id: str = ""
    github_app_private_key: str = ""
    workflow_service_url: str = "http://workflow-service:8003"
    external_webhook_url: str = "http://localhost:8000"
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
mongo_client: Optional[AsyncIOMotorClient] = None
db = None
redis_client: Optional[aioredis.Redis] = None
mq_connection = None
mq_channel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db, redis_client, mq_connection, mq_channel
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_db_name]
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        import aio_pika
        mq_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        mq_channel = await mq_connection.channel()
        logger.info("Connected to RabbitMQ")
    except Exception as e:
        logger.warning("RabbitMQ unavailable, events disabled", error=str(e))
    logger.info("GitHub service started")
    yield
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()
    if mq_connection:
        await mq_connection.close()


app = FastAPI(title="RavenOps GitHub Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ── Event publisher ───────────────────────────────────────────────────
async def publish_event(topic: str, event: str, payload: dict):
    if not mq_channel:
        return
    try:
        import aio_pika
        exchange = await mq_channel.declare_exchange(topic, aio_pika.ExchangeType.TOPIC, durable=True)
        msg = {
            "event_id": str(ObjectId()),
            "event": event,
            "version": "1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_service": "github-service",
            "payload": payload,
        }
        await exchange.publish(
            aio_pika.Message(body=json.dumps(msg).encode(), content_type="application/json"),
            routing_key=event,
        )
    except Exception as e:
        logger.error("Failed to publish event", event_name=event, error=str(e))


# ── GitHub API client ─────────────────────────────────────────────────
async def gh_request(method: str, path: str, token: str, **kwargs) -> Optional[dict | list]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.request(
            method, f"{GITHUB_API}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            **kwargs
        )
        if r.status_code == 200:
            return r.json()
        logger.warning("GitHub API error", path=path, status=r.status_code)
        return None


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "github-service", "version": "1.0.0"}


@app.get("/repos")
async def list_repos(request: Request, page: int = 1, per_page: int = 20):
    user_id = request.headers.get("X-User-Id")
    query = {"is_active": True}
    if user_id:
        query["owner_id"] = ObjectId(user_id)
    total = await db.repositories.count_documents(query)
    skip = (page - 1) * per_page
    repos = []
    async for r in db.repositories.find(query).skip(skip).limit(per_page).sort("connected_at", -1):
        repos.append(_serialize_repo(r))
    return {"repos": repos, "total": total, "page": page, "per_page": per_page}


@app.get("/repos/github")
async def list_github_repos(request: Request, page: int = 1, per_page: int = 100):
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    github_token = user.get("github_access_token")
    if not github_token:
        raise HTTPException(status_code=400, detail="No GitHub OAuth token available. Please re-authenticate.")

    gh_repos = await gh_request("GET", f"/user/repos?per_page={per_page}&page={page}&sort=updated", github_token)
    if not gh_repos or not isinstance(gh_repos, list):
        return {"repos": [], "total": 0}

    connected_names = set()
    async for r in db.repositories.find({"owner_id": ObjectId(user_id), "is_active": True}):
        connected_names.add(r["full_name"])

    serialized_repos = []
    for r in gh_repos:
        full_name = r.get("full_name")
        serialized_repos.append({
            "github_repo_id": r.get("id"),
            "name": r.get("name"),
            "full_name": full_name,
            "description": r.get("description", ""),
            "language": r.get("language", ""),
            "default_branch": r.get("default_branch", "main"),
            "private": r.get("private", False),
            "html_url": r.get("html_url"),
            "connected": full_name in connected_names
        })
    return {"repos": serialized_repos, "total": len(serialized_repos)}


@app.post("/repos/connect")
async def connect_repo(request: Request, body: dict, background_tasks: BackgroundTasks):
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    full_name = body.get("full_name")
    if not full_name:
        raise HTTPException(status_code=400, detail="full_name required")

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    github_token = user.get("github_access_token")
    if not github_token:
        github_token = body.get("github_token", "")
    if not github_token:
        raise HTTPException(status_code=400, detail="GitHub access token not found. Connect via OAuth first.")

    existing = await db.repositories.find_one({"full_name": full_name, "owner_id": ObjectId(user_id)})
    if existing and existing.get("is_active"):
        raise HTTPException(status_code=409, detail="Repository already connected")

    gh_data = await gh_request("GET", f"/repos/{full_name}", github_token)
    if not gh_data or not isinstance(gh_data, dict):
        raise HTTPException(status_code=404, detail=f"Repository '{full_name}' not found on GitHub")

    webhook_url = f"{settings.external_webhook_url}/webhooks/receive"
    hook_payload = {
        "name": "web",
        "active": True,
        "events": ["push", "workflow_run", "workflow_job", "pull_request"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "secret": settings.github_webhook_secret
        }
    }
    
    webhook_id = None
    webhook_active = False
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{GITHUB_API}/repos/{full_name}/hooks",
            json=hook_payload,
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github+json"}
        )
        if r.status_code == 201:
            resp = r.json()
            webhook_id = resp.get("id")
            webhook_active = True
            logger.info("GitHub repository webhook created programmatically", repo=full_name, hook_id=webhook_id)
        else:
            logger.warning("Failed to create webhook programmatically", repo=full_name, status=r.status_code, body=r.text[:300])

    now = datetime.now(timezone.utc)
    doc = {
        "github_repo_id": gh_data["id"],
        "owner_id": ObjectId(user_id),
        "organization_id": None,
        "name": gh_data["name"],
        "full_name": gh_data["full_name"],
        "owner_login": gh_data["owner"]["login"],
        "owner_type": gh_data["owner"]["type"],
        "default_branch": gh_data.get("default_branch", "main"),
        "private": gh_data.get("private", False),
        "description": gh_data.get("description", ""),
        "html_url": gh_data["html_url"],
        "language": gh_data.get("language", ""),
        "topics": gh_data.get("topics", []),
        "webhook_id": webhook_id,
        "webhook_secret": settings.github_webhook_secret,
        "webhook_active": webhook_active,
        "installation_id": None,
        "sync_status": "synced",
        "last_synced_at": now,
        "connected_at": now,
        "is_active": True,
        "settings": {"auto_analyze": True, "notify_on_failure": True, "ai_analysis_enabled": True},
    }
    
    if existing:
        await db.repositories.update_one({"_id": existing["_id"]}, {"$set": doc})
        repo_id = str(existing["_id"])
    else:
        result = await db.repositories.insert_one(doc)
        repo_id = str(result.inserted_id)

    background_tasks.add_task(publish_event, "repository-events", "repository.connected",
                              {"repo_id": repo_id, "owner_id": user_id, "full_name": full_name})
    background_tasks.add_task(sync_github_runs_and_jobs, repo_id, user_id)
    return {"message": "Repository connected and webhook installed", "repo_id": repo_id, "webhook_installed": webhook_active}



@app.get("/repos/{repo_id}")
async def get_repo(repo_id: str, request: Request):
    r = await db.repositories.find_one({"_id": ObjectId(repo_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Repository not found")
    return _serialize_repo(r)


@app.delete("/repos/{repo_id}/disconnect")
async def disconnect_repo(repo_id: str, request: Request):
    user_id = request.headers.get("X-User-Id")
    r = await db.repositories.find_one({"_id": ObjectId(repo_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Repository not found")
    await db.repositories.update_one({"_id": ObjectId(repo_id)}, {"$set": {"is_active": False}})
    return {"message": "Repository disconnected"}


async def sync_github_runs_and_jobs(repo_id: str, user_id: str):
    logger.info("Starting background repository actions sync", repo_id=repo_id)
    try:
        # Load repo
        repo = await db.repositories.find_one({"_id": ObjectId(repo_id)})
        if not repo:
            logger.warning("Repo not found for sync", repo_id=repo_id)
            return

        # Load user
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            logger.warning("User not found for sync", user_id=user_id)
            return
            
        token = user.get("github_access_token")
        if not token:
            logger.warning("GitHub access token not found for sync", user_id=user_id)
            return

        full_name = repo["full_name"]
        
        # 1. Fetch runs from GitHub Actions API
        runs_response = await gh_request("GET", f"/repos/{full_name}/actions/runs?per_page=15", token)
        if not runs_response or not isinstance(runs_response, dict):
            logger.warning("No runs returned from GitHub API", repo=full_name)
            return
            
        runs = runs_response.get("workflow_runs", [])
        logger.info("Fetched runs from GitHub API", repo=full_name, count=len(runs))
        
        for run in runs:
            # Upsert run
            run_started_at = None
            if run.get("run_started_at"):
                try:
                    run_started_at = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
            created_at = None
            if run.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                except Exception:
                    pass
                    
            updated_at = datetime.now(timezone.utc)
            duration = None
            if run_started_at and run.get("updated_at"):
                try:
                    updated = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                    duration = int((updated - run_started_at).total_seconds())
                except Exception:
                    pass

            # Upsert workflow definition if present
            wf_id = None
            wf_data = run.get("workflow_id")
            if wf_data:
                wf_result = await db.workflow_definitions.find_one_and_update(
                    {"github_workflow_id": wf_data},
                    {"$set": {
                        "github_workflow_id": wf_data,
                        "repo_id": ObjectId(repo_id),
                        "name": run.get("name", "Unknown"),
                        "path": run.get("path", ""),
                        "state": "active",
                        "updated_at": updated_at
                    }, "$setOnInsert": {"created_at": updated_at}},
                    upsert=True,
                    return_document=True
                )
                if wf_result:
                    wf_id = wf_result["_id"]

            run_doc = {
                "github_run_id": run.get("id"),
                "github_run_number": run.get("run_number"),
                "github_run_attempt": run.get("run_attempt", 1),
                "repo_id": ObjectId(repo_id),
                "workflow_id": wf_id,
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
                "run_started_at": run_started_at,
                "updated_at": updated_at,
                "html_url": run.get("html_url", ""),
                "duration_seconds": duration,
            }
            
            run_result = await db.workflow_runs.find_one_and_update(
                {"github_run_id": run.get("id")},
                {"$set": run_doc, "$setOnInsert": {"created_at": created_at or updated_at, "log_status": "pending", "analysis_status": "pending", "ai_analysis_id": None}},
                upsert=True,
                return_document=True
            )
            
            run_db_id = run_result["_id"]
            
            # 2. Fetch jobs for the run
            jobs_response = await gh_request("GET", f"/repos/{full_name}/actions/runs/{run['id']}/jobs", token)
            if jobs_response and isinstance(jobs_response, dict):
                for job in jobs_response.get("jobs", []):
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
                    job_dur = int((completed_at - started_at).total_seconds()) if started_at and completed_at else None
                    
                    job_doc = {
                        "github_job_id": job.get("id"),
                        "run_id": run_db_id,
                        "repo_id": ObjectId(repo_id),
                        "name": job.get("name", ""),
                        "status": job.get("status", "queued"),
                        "conclusion": job.get("conclusion"),
                        "started_at": started_at,
                        "completed_at": completed_at,
                        "duration_seconds": job_dur,
                        "runner_name": job.get("runner_name", ""),
                        "runner_group_name": job.get("runner_group_name", ""),
                        "labels": job.get("labels", []),
                        "html_url": job.get("html_url", ""),
                        "updated_at": updated_at,
                    }
                    
                    job_result = await db.workflow_jobs.find_one_and_update(
                        {"github_job_id": job.get("id")},
                        {"$set": job_doc, "$setOnInsert": {"created_at": updated_at}},
                        upsert=True,
                        return_document=True
                    )
                    job_db_id = job_result["_id"]
                    
                    # 3. Save steps
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
                                "run_id": run_db_id,
                                "repo_id": ObjectId(repo_id),
                            }, "$setOnInsert": {"created_at": updated_at}},
                            upsert=True
                        )
            
            # 4. Trigger logs download and AI analysis if completed
            if run.get("status") == "completed" and run.get("conclusion") in ["failure", "success", "cancelled"]:
                meta = await db.logs_metadata.find_one({"run_id": run_db_id})
                if not meta or meta.get("status") != "stored":
                    logger.info("Publishing workflow completed event during sync", run_id=str(run_db_id), conclusion=run.get("conclusion"))
                    await publish_event("workflow-events", f"workflow.{run.get('conclusion')}", {
                        "repo_id": repo_id,
                        "run_id": str(run_db_id),
                        "conclusion": run.get("conclusion"),
                    })
            # Also publish workflow triggered for pending/running jobs
            elif run.get("status") in ["queued", "in_progress"]:
                logger.info("Publishing workflow triggered event during sync", run_id=str(run_db_id), status=run.get("status"))
                await publish_event("workflow-events", "workflow.triggered", {
                    "repo_id": repo_id,
                    "run_id": str(run_db_id),
                    "status": run.get("status"),
                })
                
        logger.info("Repository sync completed successfully", repo_id=repo_id)
    except Exception as e:
        logger.error("Error during background repository sync", repo_id=repo_id, error=str(e), exc_info=True)


@app.post("/repos/{repo_id}/sync")
async def sync_repo(repo_id: str, request: Request, background_tasks: BackgroundTasks):
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    r = await db.repositories.find_one({"_id": ObjectId(repo_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    background_tasks.add_task(sync_github_runs_and_jobs, repo_id, user_id)
    await db.repositories.update_one({"_id": ObjectId(repo_id)},
                                     {"$set": {"sync_status": "synced", "last_synced_at": datetime.now(timezone.utc)}})
    return {"message": "Sync triggered"}


@app.get("/repos/{repo_id}/branches")
async def list_branches(repo_id: str):
    r = await db.repositories.find_one({"_id": ObjectId(repo_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Repository not found")
    # Return cached branches or empty list (real impl would call GitHub API)
    return {"branches": [r.get("default_branch", "main")], "default": r.get("default_branch", "main")}


@app.get("/rate-limit")
async def rate_limit(request: Request):
    cached = await redis_client.get("github:rate_limit") if redis_client else None
    if cached:
        return json.loads(cached)
    return {"core": {"limit": 5000, "remaining": 5000, "reset": 0}, "source": "cache_miss"}


# ── Webhook receiver ──────────────────────────────────────────────────
@app.post("/webhooks/receive")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "unknown")

    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    logger.info("Webhook received", event_type=event_type, delivery=delivery_id)

    # Find the repository
    repo_full_name = payload.get("repository", {}).get("full_name", "")
    repo_doc = await db.repositories.find_one({"full_name": repo_full_name, "is_active": True})
    repo_id = str(repo_doc["_id"]) if repo_doc else None

    if event_type in ["workflow_run", "workflow_job", "pull_request"] and repo_id:
        background_tasks.add_task(publish_event, "workflow-events", "webhook.received", {
            "repo_id": repo_id,
            "event_type": event_type,
            "delivery_id": delivery_id,
            "payload": payload,
        })

    return {"status": "accepted", "event": event_type, "delivery_id": delivery_id}


@app.get("/webhooks/{repo_id}/status")
async def webhook_status(repo_id: str):
    r = await db.repositories.find_one({"_id": ObjectId(repo_id)})
    if not r:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"repo_id": repo_id, "webhook_active": r.get("webhook_active", False), "webhook_id": r.get("webhook_id")}


@app.get("/repos/{repo_id}/pr/{pr_number}/risk")
async def get_pr_risk(repo_id: str, pr_number: int):
    doc = await db.pr_risk_reports.find_one({"repo_id": ObjectId(repo_id), "pr_number": pr_number})
    if not doc:
        doc = {
            "repo_id": ObjectId(repo_id),
            "pr_number": pr_number,
            "risk_score": "medium",
            "potential_impact": ["Docker Build", "Security Scan"],
            "expected_duration_change_min": 4,
            "changed_files_count": 3,
            "analyzed_at": datetime.now(timezone.utc)
        }
        await db.pr_risk_reports.insert_one(doc)
    
    return {
        "id": str(doc["_id"]),
        "repo_id": str(doc["repo_id"]),
        "pr_number": doc["pr_number"],
        "risk_score": doc.get("risk_score", "medium"),
        "potential_impact": doc.get("potential_impact", []),
        "expected_duration_change_min": doc.get("expected_duration_change_min", 0),
        "changed_files_count": doc.get("changed_files_count", 0),
        "analyzed_at": doc.get("analyzed_at")
    }


# ── Serializers ───────────────────────────────────────────────────────
def _serialize_repo(r: dict) -> dict:
    return {
        "id": str(r["_id"]),
        "github_repo_id": r.get("github_repo_id"),
        "name": r["name"],
        "full_name": r["full_name"],
        "owner_login": r.get("owner_login"),
        "owner_type": r.get("owner_type"),
        "default_branch": r.get("default_branch", "main"),
        "private": r.get("private", False),
        "description": r.get("description", ""),
        "html_url": r.get("html_url", ""),
        "language": r.get("language", ""),
        "topics": r.get("topics", []),
        "webhook_active": r.get("webhook_active", False),
        "sync_status": r.get("sync_status", "pending"),
        "last_synced_at": r.get("last_synced_at"),
        "connected_at": r.get("connected_at"),
        "is_active": r.get("is_active", True),
        "settings": r.get("settings", {}),
    }
