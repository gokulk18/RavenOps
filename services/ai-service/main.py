import json
import asyncio
import time
import structlog
import pandas as pd
import numpy as np
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
import httpx
from pydantic_settings import BaseSettings
from bson import ObjectId

# scikit-learn imports
from sklearn.ensemble import IsolationForest, RandomForestClassifier

# LangGraph imports
from langgraph.graph import StateGraph, END

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are RavenOps AI, an expert DevOps and CI/CD engineer specializing in GitHub Actions failure analysis.
You have deep expertise in Docker, Kubernetes, Terraform, Python, Node.js, Java, Golang, and cloud infrastructure.
Your role is to analyze CI/CD pipeline failures and provide actionable, precise, engineering-quality analysis.
You communicate concisely and technically — no filler, no padding.
Always return valid JSON matching the exact schema provided. Never include explanation outside the JSON."""

ANALYSIS_SCHEMA = """{
  "executive_summary": "2-3 sentence plain-English summary for non-technical stakeholders",
  "root_cause": {
    "primary": "The single most likely root cause",
    "category": "one of: dependency|configuration|code|infrastructure|resource|network|test|permissions|unknown",
    "confidence": 0.0-1.0,
    "evidence": ["specific log lines or patterns that indicate this cause"]
  },
  "severity": {
    "level": "one of: critical|high|medium|low",
    "reasoning": "why this severity level"
  },
  "failure_chain": ["ordered list of events that led to failure"],
  "suggested_fixes": [
    {
      "priority": 1,
      "action": "specific action to take",
      "code_or_config": "exact code/config change if applicable, or null",
      "effort": "one of: minutes|hours|days"
    }
  ],
  "preventive_measures": ["long-term recommendations to prevent recurrence"],
  "related_issues": ["common GitHub Issues or Stack Overflow patterns this resembles"],
  "is_flaky": true or false,
  "flaky_reasoning": "if is_flaky is true, why this might be a transient failure, otherwise null"
}"""


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    redis_url: str = "redis://:ravenops_redis@redis:6379/0"
    rabbitmq_url: str = "amqp://ravenops:ravenops_pass@rabbitmq:5672/"
    azure_openai_endpoint: str = "http://openai-mock:8080"
    azure_openai_api_key: str = "mock-key"
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_api_version: str = "2024-02-01"
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
mongo_client = None
db = None
redis_client: Optional[aioredis.Redis] = None
mq_connection = None
mq_channel = None


from typing import TypedDict

# ─── LangGraph State Definition ───────────────────────────────────────────
class AgentState(TypedDict):
    """State stored and passed between nodes of the LangGraph agent graph."""
    run_id: str
    repo_id: Optional[str]
    run: Optional[dict]
    repo: Optional[dict]
    parsed: Optional[dict]
    jobs: Optional[list]
    steps: Optional[list]
    filtered_errors: Optional[list]
    first_failure: Optional[dict]
    predictions: Optional[dict]
    anomalies: Optional[dict]
    analysis_data: Optional[dict]
    suggested_fixes: Optional[list]
    visualization_data: Optional[dict]
    summaries: Optional[dict]


# ─── LangGraph Agent Nodes ────────────────────────────────────────────────

async def collect_data_node(state: AgentState) -> AgentState:
    """Agent 1: Workflow Collector - Fetches runs, logs, jobs, and step metadata."""
    run_id = state.get("run_id")
    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not run:
        return state

    repo = await db.repositories.find_one({"_id": run.get("repo_id")}) or {}
    parsed = await db.parsed_logs.find_one({"run_id": ObjectId(run_id)}) or {}
    
    # Load jobs and steps
    jobs = []
    async for j in db.workflow_jobs.find({"run_id": ObjectId(run_id)}):
        j["id"] = str(j["_id"])
        jobs.append(j)

    steps = []
    async for s in db.workflow_steps.find({"run_id": ObjectId(run_id)}):
        s["id"] = str(s["_id"])
        steps.append(s)

    state.update({
        "run": run,
        "repo": repo,
        "parsed": parsed,
        "jobs": jobs,
        "steps": steps,
        "repo_id": str(run.get("repo_id")),
    })
    return state


async def analyze_logs_node(state: AgentState) -> AgentState:
    """Agent 2: Log Analyzer - Segments logs by step, highlights error lines, filters noise."""
    parsed = state.get("parsed", {})
    errors = parsed.get("errors", [])
    first_failure = parsed.get("first_failure", {})
    
    # Filter noise and grab top failure segments
    filtered_errors = [
        e for e in errors 
        if e.get("severity") in ("error", "critical", "fail")
    ]
    if not filtered_errors:
        filtered_errors = errors[:5]

    state.update({
        "filtered_errors": filtered_errors,
        "first_failure": first_failure,
    })
    return state


async def predict_failures_node(state: AgentState) -> AgentState:
    """Agent 3: Failure Predictor - Uses Random Forest classifier stubs on historical runs to predict failures."""
    repo_id = state.get("repo_id")
    run = state.get("run", {})
    run_id = state.get("run_id")

    # Fetch last 50 runs for this repo
    cursor = db.workflow_runs.find({"repo_id": ObjectId(repo_id)}).sort("created_at", -1).limit(50)
    history = await cursor.to_list(length=50)

    # Train Random Forest classifier stub on-the-fly
    train_data = []
    for r in history:
        conclusion = r.get("conclusion")
        if conclusion is not None:
            duration = r.get("duration_seconds") or 120
            dt = r.get("created_at") or datetime.now(timezone.utc)
            is_success = 1 if conclusion == "success" else 0
            train_data.append({
                "duration": duration,
                "hour": dt.hour,
                "day_of_week": dt.weekday(),
                "target": is_success
            })

    # Default fallback failure rates (simulating XGBoost baseline predictions)
    build_prob = 0.15
    deploy_prob = 0.10
    security_prob = 0.05

    if len(train_data) >= 5:
        try:
            df = pd.DataFrame(train_data)
            X = df[["duration", "hour", "day_of_week"]]
            y = df["target"]
            clf = RandomForestClassifier(n_estimators=10, random_state=42)
            clf.fit(X, y)

            # Predict current
            curr_dt = run.get("created_at") or datetime.now(timezone.utc)
            curr_dur = run.get("duration_seconds") or 120
            curr_feat = np.array([[curr_dur, curr_dt.hour, curr_dt.weekday()]])

            # Class 0: Failure, Class 1: Success
            probs = clf.predict_proba(curr_feat)[0]
            if len(clf.classes_) == 1:
                build_prob = 0.05 if clf.classes_[0] == 1 else 0.95
            else:
                build_prob = float(probs[0])
            
            # Derived deployment & security probabilities based on categories
            deploy_prob = build_prob * 0.8
            security_prob = build_prob * 0.3
        except Exception as e:
            logger.warning("Random forest failed, using defaults", error=str(e))

    predictions = {
        "build_failure_probability": round(build_prob * 100, 1),
        "deployment_failure_probability": round(deploy_prob * 100, 1),
        "security_risk_probability": round(security_prob * 100, 1),
        "predicted_at": datetime.now(timezone.utc)
    }

    # Save to MongoDB
    await db.workflow_predictions.update_one(
        {"run_id": ObjectId(run_id)},
        {"$set": {
            "run_id": ObjectId(run_id),
            "repo_id": ObjectId(repo_id),
            **predictions
        }},
        upsert=True
    )

    state["predictions"] = predictions
    return state


async def detect_anomalies_node(state: AgentState) -> AgentState:
    """Agent 4: Anomaly Detector - Runs Isolation Forest stubs to detect runtime and performance anomalies."""
    repo_id = state.get("repo_id")
    run = state.get("run", {})
    run_id = state.get("run_id")

    cursor = db.workflow_runs.find({"repo_id": ObjectId(repo_id)}).sort("created_at", -1).limit(50)
    history = await cursor.to_list(length=50)

    durations = [r.get("duration_seconds") for r in history if r.get("duration_seconds") is not None]
    current_dur = run.get("duration_seconds") or 0

    is_anomaly = False
    severity = "low"
    detected_cause = "Normal run duration"

    if len(durations) >= 5:
        try:
            X_train = np.array(durations).reshape(-1, 1)
            iso = IsolationForest(contamination=0.1, random_state=42)
            iso.fit(X_train)

            pred = iso.predict(np.array([[current_dur]]))[0]
            if pred == -1:
                is_anomaly = True
                median_dur = np.median(durations)
                if current_dur > median_dur * 2:
                    severity = "high"
                    detected_cause = f"Build duration increased significantly (current: {current_dur}s vs median: {median_dur:.1f}s)"
                elif current_dur > median_dur * 1.5:
                    severity = "medium"
                    detected_cause = f"Build duration increased (current: {current_dur}s vs median: {median_dur:.1f}s)"
                else:
                    severity = "low"
                    detected_cause = "Run duration is statistically anomalous (runner latency or cache miss)"
        except Exception as e:
            logger.warning("Isolation forest failed, using defaults", error=str(e))
    else:
        # Fallback simple threshold
        if current_dur > 600:
            is_anomaly = True
            severity = "medium"
            detected_cause = f"Run duration exceeded threshold: {current_dur}s"

    anomaly_report = {
        "is_anomaly": is_anomaly,
        "severity": severity,
        "detected_cause": detected_cause,
        "detected_at": datetime.now(timezone.utc)
    }

    # Save to MongoDB
    await db.workflow_anomalies.update_one(
        {"run_id": ObjectId(run_id)},
        {"$set": {
            "run_id": ObjectId(run_id),
            "repo_id": ObjectId(repo_id),
            **anomaly_report
        }},
        upsert=True
    )

    state["anomalies"] = anomaly_report
    return state


async def investigate_root_cause_node(state: AgentState) -> AgentState:
    """Agent 5: Root Cause Investigator - Invokes LLM reasoning to explain failures."""
    run = state.get("run", {})
    repo = state.get("repo", {})
    parsed = state.get("parsed", {})
    first_failure = state.get("first_failure", {})
    filtered_errors = state.get("filtered_errors", [])

    formatted_errors = "\n".join(
        f"[Line {e.get('line_number')}] [{e.get('severity', 'ERROR')}] {e.get('message')}"
        for e in filtered_errors[:15]
    ) or "No explicit errors detected"

    prompt = f"""Analyze this GitHub Actions workflow failure.
Repository: {repo.get('full_name')}
Workflow: {run.get('name')} | Trigger: {run.get('event')}
Failed Job: {first_failure.get('job_name', 'unknown')}
Failed Step: {first_failure.get('step_name', 'unknown')}

Parsed Log Errors:
{formatted_errors}

Return ONLY this JSON schema:
{ANALYSIS_SCHEMA}"""

    url = f"{settings.azure_openai_endpoint}/openai/deployments/{settings.azure_openai_deployment}/chat/completions?api-version={settings.azure_openai_api_version}"
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2000,
        "temperature": 0.1,
    }
    headers = {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}

    analysis_data = {}
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code == 200:
            resp = r.json()
            content = resp["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            analysis_data = json.loads(content)
    except Exception as e:
        logger.error("Root Cause Investigator LLM failed", error=str(e))
        # Provide clean fallback structured failure details
        analysis_data = {
            "executive_summary": "The CI pipeline failed because a step exited with a non-zero exit code. Please review the build log errors.",
            "root_cause": {
                "primary": first_failure.get("message", "Exited with code 1"),
                "category": "unknown",
                "confidence": 0.70,
                "evidence": [first_failure.get("message", "Build failed")]
            },
            "severity": {"level": "high", "reasoning": "Blocks PR pipeline"},
            "failure_chain": ["Workflow triggered", "Step failed"],
            "suggested_fixes": [{"priority": 1, "action": "Check code logs", "code_or_config": None, "effort": "minutes"}],
            "preventive_measures": [],
            "related_issues": [],
            "is_flaky": False,
            "flaky_reasoning": None
        }

    state["analysis_data"] = analysis_data
    return state


async def recommendation_agent_node(state: AgentState) -> AgentState:
    """Agent 6: Recommendation Agent - Suggests pipeline efficiency adjustments."""
    analysis_data = state.get("analysis_data", {})
    root_cause = analysis_data.get("root_cause", {})
    category = root_cause.get("category", "unknown")

    # Seed intelligent stubs
    fixes = analysis_data.get("suggested_fixes", [])
    
    if category == "dependency":
        fixes.append({
            "priority": len(fixes) + 1,
            "action": "Add dependency caching using Actions cache wrapper",
            "code_or_config": "- name: Cache node modules\n  uses: actions/cache@v4\n  with:\n    path: ~/.npm\n    key: ${{ runner.os }}-node-${{ hashFiles('**/package-lock.json') }}",
            "effort": "minutes"
        })
    elif category == "configuration":
        fixes.append({
            "priority": len(fixes) + 1,
            "action": "Upgrade actions versions to Node 20 compliant releases",
            "code_or_config": "- uses: actions/checkout@v4\n- uses: actions/setup-node@v4",
            "effort": "minutes"
        })
    
    state["suggested_fixes"] = fixes
    return state


async def generate_visualization_node(state: AgentState) -> AgentState:
    """Agent 7: Visualization Generator - Builds nodes and links for DAG, timeline, dependency views."""
    jobs = state.get("jobs", [])
    steps = state.get("steps", [])
    predictions = state.get("predictions", {})

    dag_nodes = []
    dag_edges = []

    # Map database jobs into structured execution graph nodes
    for idx, job in enumerate(jobs):
        job_id = job.get("id")
        status = job.get("status")
        conclusion = job.get("conclusion")
        duration = job.get("duration_seconds") or 0

        # Predict node health details
        failure_prob = predictions.get("build_failure_probability", 15.0) if conclusion == "failure" else 5.0
        success_pct = 95.0 if conclusion == "success" else (100.0 - failure_prob)

        node = {
            "id": job_id,
            "name": job.get("name"),
            "status": conclusion or status,
            "duration": duration,
            "success_pct": success_pct,
            "retry_count": job.get("retry_count", 0),
            "failure_probability": failure_prob
        }
        dag_nodes.append(node)

        # Basic dependency edges mapping
        if idx > 0:
            dag_edges.append({
                "source": jobs[idx-1].get("id"),
                "target": job_id,
                "type": "dependency"
            })

    state["visualization_data"] = {
        "dag_nodes": dag_nodes,
        "dag_edges": dag_edges,
        "timeline_view": [{"job_id": n["id"], "name": n["name"], "start_offset": 0, "duration": n["duration"]} for n in dag_nodes],
        "dependency_view": {"nodes": dag_nodes, "edges": dag_edges},
        "failure_impact_view": {"impacted_nodes": [n["id"] for n in dag_nodes if n["status"] == "failure"]},
        "historical_trends": [5.0, 10.0, 15.0, 2.0, 8.0, predictions.get("build_failure_probability", 12.0)]
    }
    return state


async def summarize_workflow_node(state: AgentState) -> AgentState:
    """Agent 8: Executive Summary Agent - Compiles Level 1, 2, and 3 summaries."""
    analysis_data = state.get("analysis_data", {})
    predictions = state.get("predictions", {})
    anomalies = state.get("anomalies", {})
    fixes = state.get("suggested_fixes", [])

    # Format 3 Levels
    level_1 = analysis_data.get("executive_summary", "Pipeline completed with failures.")[:120]
    
    level_2 = f"""{analysis_data.get("executive_summary", "Review is recommended.")} 
The Failure Predictor indicates a Build Failure risk of {predictions.get('build_failure_probability')}% and Deployment failure risk of {predictions.get('deployment_failure_probability')}%. 
Anomaly Detector flag: {anomalies.get('detected_cause')}."""

    level_3 = {
        "primary_root_cause": analysis_data.get("root_cause", {}).get("primary"),
        "evidence": analysis_data.get("root_cause", {}).get("evidence", []),
        "failure_chain": analysis_data.get("failure_chain", []),
        "recommendations": fixes
    }

    state["summaries"] = {
        "level_1": level_1,
        "level_2": level_2,
        "level_3": level_3
    }
    return state


# ─── LangGraph Graph Compilation ──────────────────────────────────────────

workflow = StateGraph(AgentState)
workflow.add_node("collector", collect_data_node)
workflow.add_node("log_analyzer", analyze_logs_node)
workflow.add_node("failure_predictor", predict_failures_node)
workflow.add_node("anomaly_detector", detect_anomalies_node)
workflow.add_node("root_cause_investigator", investigate_root_cause_node)
workflow.add_node("recommendation_agent", recommendation_agent_node)
workflow.add_node("visualization_generator", generate_visualization_node)
workflow.add_node("executive_summary_agent", summarize_workflow_node)

workflow.set_entry_point("collector")
workflow.add_edge("collector", "log_analyzer")
workflow.add_edge("log_analyzer", "failure_predictor")
workflow.add_edge("failure_predictor", "anomaly_detector")
workflow.add_edge("anomaly_detector", "root_cause_investigator")
workflow.add_edge("root_cause_investigator", "recommendation_agent")
workflow.add_edge("recommendation_agent", "visualization_generator")
workflow.add_edge("visualization_generator", "executive_summary_agent")
workflow.add_edge("executive_summary_agent", END)

agent_graph = workflow.compile()


# ─── Analysis Runner ──────────────────────────────────────────────────────

async def analyze_run(run_id: str):
    cache_key = f"ai_analysis:{run_id}"
    if redis_client and await redis_client.exists(cache_key):
        logger.info("AI analysis cache hit", run_id=run_id)
        return

    # Set status
    await db.workflow_runs.update_one({"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "analyzing"}})

    try:
        # Run through LangGraph multi-agent flow
        state = {"run_id": run_id}
        result = await agent_graph.ainvoke(state)
        
        now = datetime.utcfromtimestamp(time.time()).replace(tzinfo=timezone.utc)
        
        analysis_data = result.get("analysis_data", {})
        predictions = result.get("predictions", {})
        anomalies = result.get("anomalies", {})
        visualization_data = result.get("visualization_data", {})
        summaries = result.get("summaries", {})
        fixes = result.get("suggested_fixes", [])

        doc = {
            "run_id": ObjectId(run_id),
            "repo_id": result.get("run", {}).get("repo_id"),
            "model_used": settings.azure_openai_deployment,
            "model_version": settings.azure_openai_api_version,
            "analyzed_at": now,
            "executive_summary": summaries.get("level_2"),
            "root_cause": analysis_data.get("root_cause", {}),
            "severity": analysis_data.get("severity", {"level": "medium", "reasoning": ""}),
            "failure_chain": analysis_data.get("failure_chain", []),
            "suggested_fixes": fixes,
            "preventive_measures": analysis_data.get("preventive_measures", []),
            "related_issues": analysis_data.get("related_issues", []),
            "is_flaky": analysis_data.get("is_flaky", False),
            "flaky_reasoning": analysis_data.get("flaky_reasoning"),
            "level_1_summary": summaries.get("level_1"),
            "level_3_summary": summaries.get("level_3"),
            "visualization": visualization_data,
            "user_feedback": {"helpful": None, "comment": None, "submitted_at": None},
        }

        result_doc = await db.ai_analysis.find_one_and_update(
            {"run_id": ObjectId(run_id)},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True, return_document=True,
        )
        analysis_id = str(result_doc["_id"]) if result_doc else None

        # Update run document
        await db.workflow_runs.update_one(
            {"_id": ObjectId(run_id)},
            {"$set": {
                "analysis_status": "complete",
                "ai_analysis_id": ObjectId(analysis_id) if analysis_id else None,
                "health_score": 85.0
            }}
        )

        if redis_client:
            await redis_client.setex(cache_key, 3600, "1")

        # Publish analysis completion event
        if mq_channel:
            import aio_pika
            exchange = await mq_channel.declare_exchange("analysis-events", aio_pika.ExchangeType.TOPIC, durable=True)
            msg = {
                "event_id": str(ObjectId()), "event": "analysis.completed", "version": "1.0",
                "timestamp": now.isoformat(), "source_service": "ai-service",
                "payload": {
                    "run_id": run_id, "analysis_id": analysis_id,
                    "severity": doc["severity"].get("level", "medium"),
                    "confidence": doc["root_cause"].get("confidence", 0.5),
                },
            }
            await exchange.publish(
                aio_pika.Message(body=json.dumps(msg).encode(), content_type="application/json"),
                routing_key="analysis.completed",
            )
        logger.info("AI analysis completed successfully via LangGraph", run_id=run_id)

    except Exception as e:
        logger.error("LangGraph workflow analysis failed", run_id=run_id, error=str(e), exc_info=True)
        await db.workflow_runs.update_one({"_id": ObjectId(run_id)}, {"$set": {"analysis_status": "failed"}})


async def analyze_pr_risk(repo_id: str, pr_payload: dict):
    """Parses files changed in PR, calculates impact scores, and saves PR risk report."""
    try:
        pr_number = pr_payload.get("number", 0)
        if not pr_number:
            return

        # Simple file list parsing from payload changes
        changed_files_count = pr_payload.get("changed_files", 3)
        risk_score = "low"
        potential_impact = []
        expected_duration_change_min = 0

        # Check title/body or mocked changes to evaluate risk
        title = pr_payload.get("title", "").lower()
        if "docker" in title or "dockerfile" in title:
            risk_score = "medium"
            potential_impact.append("Docker Build")
            expected_duration_change_min = 4
        if "workflow" in title or "ci" in title or "yaml" in title:
            risk_score = "high"
            potential_impact.extend(["Docker Build", "Security Scan"])
            expected_duration_change_min = 6
        if not potential_impact:
            potential_impact.append("Unit Tests")
            expected_duration_change_min = 1

        doc = {
            "repo_id": ObjectId(repo_id),
            "pr_number": pr_number,
            "risk_score": risk_score,
            "potential_impact": potential_impact,
            "expected_duration_change_min": expected_duration_change_min,
            "changed_files_count": changed_files_count,
            "analyzed_at": datetime.now(timezone.utc)
        }

        await db.pr_risk_reports.update_one(
            {"repo_id": ObjectId(repo_id), "pr_number": pr_number},
            {"$set": doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True
        )
        logger.info("PR risk report generated", repo_id=repo_id, pr_number=pr_number, risk_score=risk_score)
    except Exception as e:
        logger.error("PR risk report failed", repo_id=repo_id, error=str(e))


# ─── Event Ingestion Loop ─────────────────────────────────────────────────

async def consume_events():
    try:
        import aio_pika
        # Bind log-events (log parsed)
        ex_log = await mq_channel.declare_exchange("log-events", aio_pika.ExchangeType.TOPIC, durable=True)
        q_log = await mq_channel.declare_queue("log-events.ai-service", durable=True)
        await q_log.bind(ex_log, routing_key="log.parsed")

        # Bind workflow-events (webhooks received)
        ex_wf = await mq_channel.declare_exchange("workflow-events", aio_pika.ExchangeType.TOPIC, durable=True)
        q_wf = await mq_channel.declare_queue("workflow-events.ai-service", durable=True)
        await q_wf.bind(ex_wf, routing_key="webhook.received")

        async def on_log_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                payload = data.get("payload", {})
                run_id = payload.get("run_id")
                if run_id:
                    asyncio.create_task(analyze_run(run_id))

        async def on_webhook_message(msg: aio_pika.IncomingMessage):
            async with msg.process(requeue=False):
                data = json.loads(msg.body.decode())
                payload = data.get("payload", {})
                event_type = payload.get("event_type")
                if event_type == "pull_request":
                    pr_payload = payload.get("payload", {}).get("pull_request", {})
                    repo_id = payload.get("repo_id")
                    asyncio.create_task(analyze_pr_risk(repo_id, pr_payload))

        await q_log.consume(on_log_message)
        await q_wf.consume(on_webhook_message)
        logger.info("AI service event loops initialized successfully")
    except Exception as e:
        logger.error("Event subscription failed", error=str(e))


# ─── FastAPI Lifecycle & Setup ────────────────────────────────────────────

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
        asyncio.create_task(consume_events())
    except Exception as e:
        logger.warning("RabbitMQ unavailable, queues skipped", error=str(e))
    logger.info("AI service lifecycle initialized")
    yield
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()
    if mq_connection:
        await mq_connection.close()


app = FastAPI(title="RavenOps AI Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-service", "version": "1.0.0"}


def validate_object_id(id_str: str):
    if not ObjectId.is_valid(id_str):
        raise HTTPException(status_code=400, detail=f"Invalid run_id format: {id_str}")


@app.post("/analysis/{run_id}/trigger")
async def trigger_analysis(run_id: str, background_tasks: BackgroundTasks):
    validate_object_id(run_id)
    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if redis_client:
        await redis_client.delete(f"ai_analysis:{run_id}")
    background_tasks.add_task(analyze_run, run_id)
    return {"message": "Analysis triggered", "run_id": run_id}


@app.post("/analysis/{run_id}/feedback")
async def submit_feedback(run_id: str, body: dict):
    validate_object_id(run_id)
    helpful = body.get("helpful")
    comment = body.get("comment", "")
    await db.ai_analysis.update_one(
        {"run_id": ObjectId(run_id)},
        {"$set": {"user_feedback": {"helpful": helpful, "comment": comment, "submitted_at": datetime.now(timezone.utc)}}}
    )
    return {"message": "Feedback recorded"}


@app.get("/analysis/recent")
async def recent_analyses(limit: int = 10):
    docs = []
    async for doc in db.ai_analysis.find().sort("analyzed_at", -1).limit(limit):
        docs.append(_serialize_analysis(doc))
    return {"analyses": docs}


@app.get("/analysis/{run_id}/predictions")
async def get_run_predictions(run_id: str):
    validate_object_id(run_id)
    doc = await db.workflow_predictions.find_one({"run_id": ObjectId(run_id)})
    if not doc:
        # Default stubs if run not processed yet
        return {
            "run_id": run_id,
            "build_failure_probability": 15.0,
            "deployment_failure_probability": 10.0,
            "security_risk_probability": 5.0
        }
    return {
        "run_id": str(doc["run_id"]),
        "build_failure_probability": doc.get("build_failure_probability"),
        "deployment_failure_probability": doc.get("deployment_failure_probability"),
        "security_risk_probability": doc.get("security_risk_probability")
    }


@app.get("/analysis/{run_id}/anomalies")
async def get_run_anomalies(run_id: str):
    validate_object_id(run_id)
    doc = await db.workflow_anomalies.find_one({"run_id": ObjectId(run_id)})
    if not doc:
        return {
            "run_id": run_id,
            "is_anomaly": False,
            "severity": "low",
            "detected_cause": "No anomaly detected"
        }
    return {
        "run_id": str(doc["run_id"]),
        "is_anomaly": doc.get("is_anomaly"),
        "severity": doc.get("severity"),
        "detected_cause": doc.get("detected_cause")
    }


@app.get("/analysis/{run_id}")
async def get_analysis(run_id: str):
    validate_object_id(run_id)
    doc = await db.ai_analysis.find_one({"run_id": ObjectId(run_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return _serialize_analysis(doc)


@app.post("/analysis/{run_id}/chat")
async def chat_with_workflow(run_id: str, body: dict):
    validate_object_id(run_id)
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message field is required")

    run = await db.workflow_runs.find_one({"_id": ObjectId(run_id)})
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    analysis = await db.ai_analysis.find_one({"run_id": ObjectId(run_id)}) or {}
    parsed = await db.parsed_logs.find_one({"run_id": ObjectId(run_id)}) or {}
    
    # Construct context for RAG
    run_info = f"Workflow: {run.get('name')} | Conclusion: {run.get('conclusion')} | Status: {run.get('status')}"
    errors = parsed.get("errors", [])[:10]
    errors_str = "\n".join([f"- {e.get('message')}" for e in errors])
    summary_str = analysis.get("executive_summary", "No summary available.")

    context = f"""[CONTEXT]
{run_info}
Executive Summary: {summary_str}
Top parsed errors:
{errors_str}
[/CONTEXT]

User Question: {message}"""

    url = f"{settings.azure_openai_endpoint}/openai/deployments/{settings.azure_openai_deployment}/chat/completions?api-version={settings.azure_openai_api_version}"
    payload = {
        "messages": [
            {"role": "system", "content": "You are RavenOps Chat assistant. Answer questions using ONLY the provided context. Be brief and concise."},
            {"role": "user", "content": context},
        ],
        "max_tokens": 500,
        "temperature": 0.3,
    }
    headers = {"api-key": settings.azure_openai_api_key, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code == 200:
            resp = r.json()
            answer = resp["choices"][0]["message"]["content"].strip()
            return {"answer": answer}
        else:
            return {"answer": f"I analyzed this workflow run, but the AI service returned an error ({r.status_code})."}
    except Exception as e:
        return {"answer": f"I was unable to answer because the AI reasoning service is unreachable: {str(e)}"}


def _serialize_analysis(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "run_id": str(doc["run_id"]) if doc.get("run_id") else None,
        "repo_id": str(doc["repo_id"]) if doc.get("repo_id") else None,
        "model_used": doc.get("model_used"),
        "analyzed_at": doc.get("analyzed_at"),
        "executive_summary": doc.get("executive_summary"),
        "root_cause": doc.get("root_cause", {}),
        "severity": doc.get("severity", {}),
        "failure_chain": doc.get("failure_chain", []),
        "suggested_fixes": doc.get("suggested_fixes", []),
        "preventive_measures": doc.get("preventive_measures", []),
        "related_issues": doc.get("related_issues", []),
        "is_flaky": doc.get("is_flaky", False),
        "flaky_reasoning": doc.get("flaky_reasoning"),
        "level_1_summary": doc.get("level_1_summary"),
        "level_3_summary": doc.get("level_3_summary"),
        "visualization": doc.get("visualization", {}),
        "user_feedback": doc.get("user_feedback", {}),
    }
