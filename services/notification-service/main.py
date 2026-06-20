import json
import hashlib
import asyncio
import email.mime.multipart
import email.mime.text
import structlog
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import httpx
from pydantic_settings import BaseSettings
from bson import ObjectId

logger = structlog.get_logger()

SEVERITY_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@ravenops.local"
    slack_webhook_url: str = ""
    teams_webhook_url: str = ""
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
    logger.info("Notification service started")
    yield
    if mongo_client:
        mongo_client.close()
    if mq_connection:
        await mq_connection.close()


async def consume_events():
    try:
        import aio_pika
        # Subscribe to workflow failures & triggers
        ex_wf = await mq_channel.declare_exchange("workflow-events", aio_pika.ExchangeType.TOPIC, durable=True)
        q_wf = await mq_channel.declare_queue("workflow-events.notification-service", durable=True)
        await q_wf.bind(ex_wf, routing_key="workflow.failure")
        await q_wf.bind(ex_wf, routing_key="workflow.triggered")

        # Subscribe to completed analyses
        ex_ai = await mq_channel.declare_exchange("analysis-events", aio_pika.ExchangeType.TOPIC, durable=True)
        q_ai = await mq_channel.declare_queue("analysis-events.notification-service", durable=True)
        await q_ai.bind(ex_ai, routing_key="analysis.completed")

        async def on_wf_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                event = data.get("event")
                payload = data.get("payload", {})
                if event == "workflow.failure":
                    asyncio.create_task(handle_workflow_failure(payload))
                elif event == "workflow.triggered":
                    asyncio.create_task(handle_workflow_triggered(payload))

        async def on_ai_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                payload = data.get("payload", {})
                severity = payload.get("severity", "low")
                if severity in ("critical", "high"):
                    asyncio.create_task(handle_analysis_completed(payload))

        await q_wf.consume(on_wf_message)
        await q_ai.consume(on_ai_message)
    except Exception as e:
        logger.error("Event subscription failed", error=str(e))


async def handle_workflow_triggered(payload: dict):
    run_id = payload.get("run_id", "")
    repo_id = payload.get("repo_id", "")
    key = _dedup_key("workflow.triggered", run_id)
    if await is_duplicate(key, window_minutes=5):
        return

    run = await db.workflow_runs.find_one({"github_run_id": int(run_id)}) if run_id.isdigit() else None
    if not run and run_id:
        try:
            run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        except Exception:
            pass

    repo = None
    if repo_id:
        try:
            repo = await db.repositories.find_one({"_id": ObjectId(repo_id)})
        except Exception:
            pass

    notification_data = {
        "type": "workflow_triggered",
        "run_id": str(run["_id"]) if run else run_id,
        "repo_name": repo["full_name"] if repo else "unknown",
        "run_number": run.get("github_run_number", "?") if run else "?",
        "branch": run.get("head_branch", "unknown") if run else "unknown",
        "actor": run.get("triggering_actor", {}).get("login", "unknown") if run else "unknown",
        "duration": None,
        "html_url": run.get("html_url", "#") if run else "#",
    }

    await record_notification(key, notification_data)
    await dispatch_notifications(notification_data)
    logger.info("Workflow triggered notification sent", run_id=run_id)


def _dedup_key(event_type: str, entity_id: str) -> str:
    return hashlib.md5(f"{event_type}:{entity_id}".encode()).hexdigest()


async def is_duplicate(key: str, window_minutes: int = 15) -> bool:
    """Check if we already sent this notification recently (stored in MongoDB)."""
    cutoff = datetime.now(timezone.utc).timestamp() - (window_minutes * 60)
    existing = await db.notifications.find_one({"dedup_key": key, "sent_at": {"$gt": cutoff}})
    return existing is not None


async def record_notification(key: str, data: dict):
    now = datetime.now(timezone.utc)
    await db.notifications.insert_one({
        "dedup_key": key, "data": data, "sent_at": now.timestamp(),
        "created_at": now, "read": False,
    })


async def handle_workflow_failure(payload: dict):
    run_id = payload.get("run_id", "")
    repo_id = payload.get("repo_id", "")
    key = _dedup_key("workflow.failure", run_id)
    if await is_duplicate(key):
        return

    run = await db.workflow_runs.find_one({"github_run_id": int(run_id)}) if run_id.isdigit() else None
    if not run and run_id:
        try:
            run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
        except Exception:
            pass

    repo = None
    if repo_id:
        try:
            repo = await db.repositories.find_one({"_id": ObjectId(repo_id)})
        except Exception:
            pass

    notification_data = {
        "type": "workflow_failure",
        "run_id": run_id,
        "repo_name": repo["full_name"] if repo else "unknown",
        "run_number": run.get("github_run_number", "?") if run else "?",
        "branch": run.get("head_branch", "unknown") if run else "unknown",
        "actor": run.get("triggering_actor", {}).get("login", "unknown") if run else "unknown",
        "duration": run.get("duration_seconds") if run else None,
        "html_url": run.get("html_url", "#") if run else "#",
    }

    await record_notification(key, notification_data)
    await dispatch_notifications(notification_data)
    logger.info("Workflow failure notification sent", run_id=run_id)


async def handle_analysis_completed(payload: dict):
    run_id = payload.get("run_id", "")
    severity = payload.get("severity", "medium")
    key = _dedup_key("analysis.completed", run_id)
    if await is_duplicate(key):
        return

    analysis = await db.ai_analysis.find_one({"run_id": ObjectId(run_id)}) if run_id else None
    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)}) if run_id else None
    repo = await db.repositories.find_one({"_id": run["repo_id"]}) if run and run.get("repo_id") else None

    notification_data = {
        "type": "analysis_completed",
        "run_id": run_id,
        "severity": severity,
        "severity_emoji": SEVERITY_EMOJI.get(severity, "⚪"),
        "repo_name": repo["full_name"] if repo else "unknown",
        "executive_summary": analysis.get("executive_summary", "") if analysis else "",
        "root_cause_category": analysis.get("root_cause", {}).get("category", "unknown") if analysis else "unknown",
        "confidence": analysis.get("root_cause", {}).get("confidence", 0) if analysis else 0,
    }

    await record_notification(key, notification_data)
    await dispatch_notifications(notification_data)


async def dispatch_notifications(data: dict):
    """Dispatch to all configured channels."""
    tasks = []
    if settings.slack_webhook_url:
        tasks.append(send_slack(data))
    if settings.teams_webhook_url:
        tasks.append(send_teams(data))
    # Always try email (mailhog in dev)
    tasks.append(send_email(data))
    await asyncio.gather(*tasks, return_exceptions=True)


async def send_slack(data: dict):
    """Send Slack Block Kit message."""
    repo = data.get("repo_name", "unknown")
    ntype = data.get("type")

    if ntype == "workflow_failure":
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"🔴 Pipeline Failure — {repo}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Run:* #{data.get('run_number', '?')}"},
                {"type": "mrkdwn", "text": f"*Branch:* `{data.get('branch', 'unknown')}`"},
                {"type": "mrkdwn", "text": f"*Triggered by:* {data.get('actor', 'unknown')}"},
                {"type": "mrkdwn", "text": f"*Duration:* {data.get('duration', 'N/A')}s"},
            ]},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "View Run"},
                 "url": data.get("html_url", "#"), "style": "primary"},
            ]},
        ]
    else:
        severity = data.get("severity", "medium")
        emoji = data.get("severity_emoji", "⚪")
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} AI Analysis — {repo}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": data.get("executive_summary", "")}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Severity:* {severity.upper()}"},
                {"type": "mrkdwn", "text": f"*Root Cause:* {data.get('root_cause_category', 'unknown')}"},
                {"type": "mrkdwn", "text": f"*Confidence:* {round(data.get('confidence', 0) * 100)}%"},
            ]},
        ]

    payload = {"blocks": blocks}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(settings.slack_webhook_url, json=payload)
        if r.status_code != 200:
            logger.warning("Slack notification failed", status=r.status_code)
    except Exception as e:
        logger.error("Slack send error", error=str(e))


async def send_teams(data: dict):
    """Send Microsoft Teams Adaptive Card."""
    repo = data.get("repo_name", "unknown")
    ntype = data.get("type")
    color = "attention" if ntype == "workflow_failure" else "warning"
    title = f"🔴 Pipeline Failure — {repo}" if ntype == "workflow_failure" else f"AI Analysis — {repo}"

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.5",
                "body": [
                    {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "color": color},
                    {"type": "FactSet", "facts": [
                        {"title": "Repository", "value": repo},
                        {"title": "Branch", "value": data.get("branch", "N/A")},
                        {"title": "Triggered By", "value": data.get("actor", "N/A")},
                    ]},
                ],
                "actions": [
                    {"type": "Action.OpenUrl", "title": "View Details", "url": data.get("html_url", "#")},
                ],
            },
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(settings.teams_webhook_url, json=card)
        if r.status_code not in (200, 202):
            logger.warning("Teams notification failed", status=r.status_code)
    except Exception as e:
        logger.error("Teams send error", error=str(e))


async def send_email(data: dict):
    """Send HTML email via SMTP (MailHog in dev)."""
    import aiosmtplib
    repo = data.get("repo_name", "unknown")
    ntype = data.get("type")

    subject = (f"[RavenOps] 🔴 Pipeline Failure: {repo}"
               if ntype == "workflow_failure"
               else f"[RavenOps] AI Analysis Complete: {repo}")

    if ntype == "workflow_failure":
        body = f"""
        <html><body style="font-family: Inter, sans-serif; background: #0D0D0D; color: #F0F0F0; padding: 32px;">
        <div style="max-width: 600px; margin: 0 auto; background: #151515; border-radius: 12px; border: 1px solid #2A2A2A; padding: 32px;">
          <div style="border-left: 4px solid #DC2626; padding-left: 16px; margin-bottom: 24px;">
            <h1 style="color: #DC2626; margin: 0; font-size: 20px;">🔴 Pipeline Failure</h1>
            <p style="color: #A0A0A0; margin: 4px 0;">{repo}</p>
          </div>
          <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px; color: #A0A0A0;">Run</td><td style="color: #F0F0F0;">#{data.get("run_number", "?")}</td></tr>
            <tr><td style="padding: 8px; color: #A0A0A0;">Branch</td><td style="color: #22C55E; font-family: monospace;">{data.get("branch", "unknown")}</td></tr>
            <tr><td style="padding: 8px; color: #A0A0A0;">Triggered by</td><td style="color: #F0F0F0;">{data.get("actor", "unknown")}</td></tr>
            <tr><td style="padding: 8px; color: #A0A0A0;">Duration</td><td style="color: #F0F0F0;">{data.get("duration", "N/A")}s</td></tr>
          </table>
          <a href="{data.get("html_url", "#")}" style="display: inline-block; margin-top: 24px; background: #22C55E; color: #0D0D0D; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600;">View Run →</a>
        </div>
        </body></html>
        """
    else:
        body = f"""
        <html><body style="font-family: Inter, sans-serif; background: #0D0D0D; color: #F0F0F0; padding: 32px;">
        <div style="max-width: 600px; margin: 0 auto; background: #151515; border-radius: 12px; border: 1px solid #2A2A2A; padding: 32px;">
          <div style="border: 1px solid; border-image: linear-gradient(135deg, #7C3AED, #A855F7) 1; padding: 16px; border-radius: 8px; margin-bottom: 24px;">
            <h1 style="margin: 0; font-size: 18px; background: linear-gradient(135deg, #7C3AED, #A855F7); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">🤖 AI Analysis Complete</h1>
          </div>
          <p style="color: #F0F0F0; line-height: 1.7;">{data.get("executive_summary", "")}</p>
          <div style="background: #1C1C1C; border-radius: 8px; padding: 16px; margin-top: 16px;">
            <p style="margin: 0; color: #A0A0A0;">Root Cause Category: <strong style="color: #A855F7;">{data.get("root_cause_category", "unknown")}</strong></p>
            <p style="margin: 8px 0 0; color: #A0A0A0;">Severity: <strong style="color: #F59E0B;">{data.get("severity", "medium").upper()}</strong></p>
          </div>
        </div>
        </body></html>
        """

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = "team@ravenops.local"
    msg.attach(email.mime.text.MIMEText(body, "html"))

    try:
        await aiosmtplib.send(
            msg, hostname=settings.smtp_host, port=settings.smtp_port,
            username=settings.smtp_user or None, password=settings.smtp_password or None,
            use_tls=False,
        )
        logger.info("Email notification sent")
    except Exception as e:
        logger.warning("Email send failed", error=str(e))


app = FastAPI(title="RavenOps Notification Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification-service", "version": "1.0.0"}


@app.get("/notifications")
async def list_notifications(page: int = 1, per_page: int = 20, unread_only: bool = False):
    query: dict = {}
    if unread_only:
        query["read"] = False
    total = await db.notifications.count_documents(query)
    skip = (page - 1) * per_page
    notifs = []
    async for n in db.notifications.find(query).skip(skip).limit(per_page).sort("created_at", -1):
        notifs.append({
            "id": str(n["_id"]), "type": n.get("data", {}).get("type"),
            "repo_name": n.get("data", {}).get("repo_name"),
            "read": n.get("read", False), "created_at": n.get("created_at"),
            "data": n.get("data", {}),
        })
    return {"notifications": notifs, "total": total, "page": page, "per_page": per_page}


@app.post("/notifications/{notification_id}/read")
async def mark_read(notification_id: str):
    await db.notifications.update_one({"_id": ObjectId(notification_id)}, {"$set": {"read": True}})
    return {"message": "Marked as read"}


@app.post("/notifications/read-all")
async def mark_all_read():
    result = await db.notifications.update_many({"read": False}, {"$set": {"read": True}})
    return {"message": f"Marked {result.modified_count} notifications as read"}
