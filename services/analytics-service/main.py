import json
import asyncio
import statistics
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
from bson import ObjectId

logger = structlog.get_logger()


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
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
        asyncio.create_task(consume_events())
    except Exception as e:
        logger.warning("RabbitMQ unavailable", error=str(e))
    logger.info("Analytics service started")
    yield
    if mongo_client:
        mongo_client.close()
    if mq_connection:
        await mq_connection.close()


async def consume_events():
    try:
        import aio_pika
        ex_wf = await mq_channel.declare_exchange("workflow-events", aio_pika.ExchangeType.TOPIC, durable=True)
        q_wf = await mq_channel.declare_queue("workflow-events.analytics-service", durable=True)
        await q_wf.bind(ex_wf, routing_key="workflow.completed")
        await q_wf.bind(ex_wf, routing_key="workflow.failure")

        async def on_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                payload = data.get("payload", {})
                repo_id = payload.get("repo_id")
                if repo_id:
                    asyncio.create_task(recompute_repo_snapshot(repo_id))

        await q_wf.consume(on_message)
    except Exception as e:
        logger.error("Event subscription failed", error=str(e))


async def recompute_repo_snapshot(repo_id: str):
    """Recompute daily analytics snapshot for a repository."""
    try:
        now = datetime.now(timezone.utc)
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)

        query = {
            "repo_id": ObjectId(repo_id),
            "created_at": {"$gte": period_start - timedelta(days=30), "$lt": now},
        }

        durations = []
        total = success = failure = cancelled = 0
        error_categories: dict[str, int] = {}

        async for run in db.workflow_runs.find(query):
            total += 1
            conclusion = run.get("conclusion")
            if conclusion == "success":
                success += 1
            elif conclusion in ("failure", "timed_out", "startup_failure"):
                failure += 1
            elif conclusion == "cancelled":
                cancelled += 1
            d = run.get("duration_seconds")
            if d and d > 0:
                durations.append(d)

        success_rate = round(success / total, 4) if total > 0 else 0.0
        failure_rate = round(failure / total, 4) if total > 0 else 0.0

        sorted_durations = sorted(durations)
        p50 = float(statistics.median(sorted_durations)) if sorted_durations else 0.0
        p95 = float(sorted_durations[int(len(sorted_durations) * 0.95)]) if sorted_durations else 0.0
        p99 = float(sorted_durations[int(len(sorted_durations) * 0.99)]) if sorted_durations else 0.0
        avg_dur = round(sum(sorted_durations) / len(sorted_durations), 1) if sorted_durations else 0.0

        # Count flaky runs in last 30 days
        flaky_count = await db.ai_analysis.count_documents({
            "repo_id": ObjectId(repo_id),
            "analyzed_at": {"$gte": period_start - timedelta(days=30)},
            "is_flaky": True
        })

        # Error category distribution
        async for parsed in db.parsed_logs.find({"repo_id": ObjectId(repo_id)}):
            for err in parsed.get("errors", []):
                cat = err.get("category", "unknown")
                error_categories[cat] = error_categories.get(cat, 0) + 1

        security_error_count = error_categories.get("security", 0) + error_categories.get("permissions", 0)

        # Health score: weighted composite (0-100)
        # 1. Success rate (40%)
        # 2. Duration baseline (20%) - baseline benchmark of 300s
        # 3. Flakiness (10%)
        # 4. Security issues (10%)
        # 5. Failure frequency (20%)
        dur_score = min(1.0, 300.0 / max(avg_dur, 1.0)) if avg_dur > 0 else 1.0
        flaky_score = max(0.0, 1.0 - (flaky_count / max(total, 1.0))) if total > 0 else 1.0
        sec_score = max(0.0, 1.0 - (security_error_count / 5.0))
        freq_score = max(0.0, 1.0 - (failure / max(total, 1.0))) if total > 0 else 1.0

        health_score = round(
            (success_rate * 40.0)
            + (dur_score * 20.0)
            + (flaky_score * 10.0)
            + (sec_score * 10.0)
            + (freq_score * 20.0)
        , 1)


        top_errors = sorted(
            [{"category": k, "count": v, "percentage": round(v / max(sum(error_categories.values()), 1) * 100, 1)}
             for k, v in error_categories.items()],
            key=lambda x: x["count"], reverse=True
        )[:10]

        snapshot = {
            "scope": "repo",
            "scope_id": ObjectId(repo_id),
            "period": "daily",
            "period_start": period_start,
            "period_end": period_end,
            "metrics": {
                "total_runs": total,
                "successful_runs": success,
                "failed_runs": failure,
                "cancelled_runs": cancelled,
                "success_rate": success_rate,
                "failure_rate": failure_rate,
                "avg_duration_seconds": avg_dur,
                "p50_duration": p50,
                "p95_duration": p95,
                "p99_duration": p99,
                "mttr_seconds": None,
                "health_score": health_score,
                "trend_direction": "stable",
            },
            "top_errors": top_errors,
            "computed_at": now,
        }

        await db.analytics_snapshots.update_one(
            {"scope": "repo", "scope_id": ObjectId(repo_id), "period": "daily", "period_start": period_start},
            {"$set": snapshot, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    except Exception as e:
        logger.error("Snapshot recompute failed", repo_id=repo_id, error=str(e))


app = FastAPI(title="RavenOps Analytics Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "analytics-service", "version": "1.0.0"}


@app.get("/analytics/overview")
async def overview():
    """Dashboard overview: aggregate metrics across all repos."""
    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)
    since_7d = now - timedelta(days=7)
    since_24h = now - timedelta(hours=24)

    total_runs = await db.workflow_runs.count_documents({"created_at": {"$gte": since_30d}})
    failed_30d = await db.workflow_runs.count_documents({"created_at": {"$gte": since_30d}, "conclusion": "failure"})
    success_30d = await db.workflow_runs.count_documents({"created_at": {"$gte": since_30d}, "conclusion": "success"})
    in_progress = await db.workflow_runs.count_documents({"status": "in_progress"})
    total_repos = await db.repositories.count_documents({"is_active": True})

    # Runs in last 24h
    runs_24h = await db.workflow_runs.count_documents({"created_at": {"$gte": since_24h}})
    failed_24h = await db.workflow_runs.count_documents({"created_at": {"$gte": since_24h}, "conclusion": "failure"})

    success_rate_30d = round(success_30d / max(total_runs, 1) * 100, 1)
    failure_rate_30d = round(failed_30d / max(total_runs, 1) * 100, 1)

    # Average duration
    durations = []
    async for r in db.workflow_runs.find({"created_at": {"$gte": since_7d}, "duration_seconds": {"$gt": 0}}):
        durations.append(r["duration_seconds"])
    avg_duration = round(sum(durations) / len(durations), 0) if durations else 0

    # Recent failures
    recent_failures = []
    async for r in db.workflow_runs.find({"conclusion": "failure"}).sort("created_at", -1).limit(5):
        recent_failures.append({
            "id": str(r["_id"]), "name": r.get("name"), "repo_id": str(r.get("repo_id", "")),
            "head_branch": r.get("head_branch"), "created_at": r.get("created_at"),
            "duration_seconds": r.get("duration_seconds"), "analysis_status": r.get("analysis_status"),
        })

    return {
        "total_repos": total_repos,
        "total_runs_30d": total_runs,
        "success_rate_30d": success_rate_30d,
        "failure_rate_30d": failure_rate_30d,
        "in_progress": in_progress,
        "runs_24h": runs_24h,
        "failed_24h": failed_24h,
        "avg_duration_seconds": avg_duration,
        "recent_failures": recent_failures,
    }


@app.get("/analytics/repos/{repo_id}")
async def repo_analytics(repo_id: str, days: int = 30):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    query = {"repo_id": ObjectId(repo_id), "created_at": {"$gte": since}}

    total = await db.workflow_runs.count_documents(query)
    success = await db.workflow_runs.count_documents({**query, "conclusion": "success"})
    failed = await db.workflow_runs.count_documents({**query, "conclusion": "failure"})

    durations = []
    async for r in db.workflow_runs.find({**query, "duration_seconds": {"$gt": 0}}):
        durations.append(r["duration_seconds"])
    sorted_d = sorted(durations)

    return {
        "repo_id": repo_id,
        "period_days": days,
        "total_runs": total,
        "successful_runs": success,
        "failed_runs": failed,
        "success_rate": round(success / max(total, 1) * 100, 1),
        "failure_rate": round(failed / max(total, 1) * 100, 1),
        "avg_duration": round(sum(sorted_d) / len(sorted_d), 1) if sorted_d else 0,
        "p50_duration": sorted_d[len(sorted_d) // 2] if sorted_d else 0,
        "p95_duration": sorted_d[int(len(sorted_d) * 0.95)] if sorted_d else 0,
    }


@app.get("/analytics/repos/{repo_id}/trends")
async def repo_trends(repo_id: str, days: int = 30):
    """Returns daily bucketed run counts for trend charts."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    buckets: dict[str, dict] = {}

    for i in range(days):
        day = (since + timedelta(days=i)).strftime("%Y-%m-%d")
        buckets[day] = {"date": day, "total": 0, "success": 0, "failure": 0, "avg_duration": 0, "_durations": []}

    async for r in db.workflow_runs.find({"repo_id": ObjectId(repo_id), "created_at": {"$gte": since}}):
        day = r["created_at"].strftime("%Y-%m-%d")
        if day in buckets:
            buckets[day]["total"] += 1
            c = r.get("conclusion")
            if c == "success":
                buckets[day]["success"] += 1
            elif c == "failure":
                buckets[day]["failure"] += 1
            d = r.get("duration_seconds")
            if d:
                buckets[day]["_durations"].append(d)

    for b in buckets.values():
        durs = b.pop("_durations", [])
        b["avg_duration"] = round(sum(durs) / len(durs), 1) if durs else 0

    return {"trends": list(buckets.values()), "period_days": days}


@app.get("/analytics/repos/{repo_id}/health")
async def repo_health(repo_id: str):
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=7)
    query = {"repo_id": ObjectId(repo_id), "created_at": {"$gte": since_7d}}

    total = await db.workflow_runs.count_documents(query)
    success = await db.workflow_runs.count_documents({**query, "conclusion": "success"})
    failure = await db.workflow_runs.count_documents({**query, "conclusion": "failure"})
    sr = success / max(total, 1)
    fr = failure / max(total, 1)
    health_score = round(sr * 70 + (1 - fr) * 30, 1)

    snapshot = await db.analytics_snapshots.find_one(
        {"scope": "repo", "scope_id": ObjectId(repo_id), "period": "daily"},
        sort=[("period_start", -1)]
    )

    return {
        "repo_id": repo_id,
        "health_score": health_score,
        "total_runs_7d": total,
        "success_rate_7d": round(sr * 100, 1),
        "failure_rate_7d": round(fr * 100, 1),
        "top_errors": snapshot.get("top_errors", []) if snapshot else [],
        "trend_direction": "stable",
    }


@app.get("/analytics/failures/top")
async def top_failures(days: int = 7, limit: int = 10):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    pipeline = [
        {"$match": {"conclusion": "failure", "created_at": {"$gte": since}}},
        {"$group": {"_id": "$repo_id", "failure_count": {"$sum": 1}}},
        {"$sort": {"failure_count": -1}},
        {"$limit": limit},
    ]
    results = []
    async for doc in db.workflow_runs.aggregate(pipeline):
        repo = await db.repositories.find_one({"_id": doc["_id"]}) if doc["_id"] else None
        results.append({
            "repo_id": str(doc["_id"]) if doc["_id"] else None,
            "repo_name": repo["full_name"] if repo else "unknown",
            "failure_count": doc["failure_count"],
        })
    return {"top_failing_repos": results, "period_days": days}


@app.get("/analytics/heatmap")
async def failure_heatmap(days: int = 7):
    """Return 7×24 grid of failure counts for heatmap visualization."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    grid: dict[str, dict[str, int]] = {}

    for d in range(days):
        day_label = (since + timedelta(days=d)).strftime("%a")
        grid[day_label] = {str(h): 0 for h in range(24)}

    async for r in db.workflow_runs.find({"conclusion": "failure", "created_at": {"$gte": since}}):
        day_label = r["created_at"].strftime("%a")
        hour = str(r["created_at"].hour)
        if day_label in grid:
            grid[day_label][hour] = grid[day_label].get(hour, 0) + 1

    return {"heatmap": grid, "period_days": days}


@app.get("/analytics/errors/distribution")
async def error_distribution(days: int = 30, repo_id: Optional[str] = None):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    query: dict = {"parsed_at": {"$gte": since}}
    if repo_id:
        query["repo_id"] = ObjectId(repo_id)

    categories: dict[str, int] = {}
    async for doc in db.parsed_logs.find(query):
        for err in doc.get("errors", []):
            cat = err.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

    total = sum(categories.values()) or 1
    dist = sorted(
        [{"category": k, "count": v, "percentage": round(v / total * 100, 1)} for k, v in categories.items()],
        key=lambda x: x["count"], reverse=True,
    )
    return {"distribution": dist, "total_errors": total, "period_days": days}


@app.get("/analytics/mttr")
async def mttr_trends(repo_id: Optional[str] = None, days: int = 30):
    """Compute mean time to recovery grouped by day."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    query: dict = {"created_at": {"$gte": since}}
    if repo_id:
        query["repo_id"] = ObjectId(repo_id)

    # MTTR = time from failure to next success on same branch
    daily_mttr: dict[str, list] = {}
    async for run in db.workflow_runs.find({**query, "conclusion": "failure"}).sort("created_at", 1):
        branch = run.get("head_branch", "")
        failed_at = run.get("created_at")
        next_success = await db.workflow_runs.find_one(
            {"repo_id": run.get("repo_id"), "head_branch": branch,
             "conclusion": "success", "created_at": {"$gt": failed_at}},
            sort=[("created_at", 1)],
        )
        if next_success:
            mttr_s = (next_success["created_at"] - failed_at).total_seconds()
            day = failed_at.strftime("%Y-%m-%d")
            daily_mttr.setdefault(day, []).append(mttr_s)

    result = []
    for day, values in sorted(daily_mttr.items()):
        result.append({"date": day, "avg_mttr_seconds": round(sum(values) / len(values), 0), "sample_size": len(values)})

    return {"mttr_by_day": result, "period_days": days}


@app.get("/analytics/anomalies")
async def detect_anomalies(days: int = 7):
    """Simple anomaly detection: repos with failure_rate > 50% in last N days."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    anomalies = []

    async for repo in db.repositories.find({"is_active": True}):
        repo_id = repo["_id"]
        total = await db.workflow_runs.count_documents({"repo_id": repo_id, "created_at": {"$gte": since}})
        if total < 3:
            continue
        failed = await db.workflow_runs.count_documents({"repo_id": repo_id, "created_at": {"$gte": since}, "conclusion": "failure"})
        fr = failed / total
        if fr > 0.5:
            anomalies.append({
                "repo_id": str(repo_id), "repo_name": repo.get("full_name"),
                "failure_rate": round(fr * 100, 1), "total_runs": total, "failed_runs": failed,
                "type": "high_failure_rate", "severity": "critical" if fr > 0.8 else "high",
            })

    return {"anomalies": anomalies, "period_days": days}
