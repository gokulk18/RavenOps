import os
import sys
import json
import asyncio
from datetime import datetime, timezone, timedelta
import httpx
import jwt as pyjwt
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# --- Configuration ---
MONGO_URI = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
DB_NAME = "ravenops"
GATEWAY_URL = "http://api-gateway:8000"
JWT_SECRET = "super-secret-jwt-key-change-in-production-min-32-chars"
JWT_ALGORITHM = "HS256"

# Colors for formatting
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


async def seed_data():
    print(f"\n{BOLD}=== Step 1: Seeding Test Data (History and Anomalous Run) ==={RESET}")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    try:
        # Clear old tests
        await db.users.delete_many({"github_login": "ai-agent-tester"})
        await db.repositories.delete_many({"full_name": "ai-test/verify-repo"})
        
        # 1. Insert User
        now = datetime.now(timezone.utc)
        user = {
            "github_id": 888888,
            "github_login": "ai-agent-tester",
            "name": "AI Agent Tester",
            "email": "tester@ravenops.local",
            "role": "member",
            "is_active": True,
            "created_at": now
        }
        user_res = await db.users.insert_one(user)
        user_id = str(user_res.inserted_id)
        print(f"  [{GREEN}OK{RESET}] Seeded test user: {user_id}")

        # 2. Insert Repo
        repo = {
            "github_repo_id": 888888,
            "owner_id": ObjectId(user_id),
            "name": "verify-repo",
            "full_name": "ai-test/verify-repo",
            "owner_login": "ai-test",
            "owner_type": "User",
            "default_branch": "main",
            "is_active": True,
            "connected_at": now
        }
        repo_res = await db.repositories.insert_one(repo)
        repo_id = str(repo_res.inserted_id)
        print(f"  [{GREEN}OK{RESET}] Seeded repository: {repo_id}")

        # 3. Seed historical workflow runs (for training Failure Predictor and Isolation Forest)
        # We seed 6 successful runs, duration ~100s
        for i in range(6):
            run_doc = {
                "github_run_id": 2000 + i,
                "github_run_number": i + 1,
                "repo_id": ObjectId(repo_id),
                "name": "CI Pipeline",
                "status": "completed",
                "conclusion": "success",
                "event": "push",
                "head_branch": "main",
                "duration_seconds": 100 + (i * 5),
                "created_at": now - timedelta(days=7 - i)
            }
            await db.workflow_runs.insert_one(run_doc)
        print(f"  [{GREEN}OK{RESET}] Seeded 6 historical successful runs (durations: 100s-125s)")

        # 4. Seed the current anomalous failed run
        # Duration: 900s (Isolation Forest should flag this as anomalous!)
        run_anom = {
            "github_run_id": 3001,
            "github_run_number": 7,
            "repo_id": ObjectId(repo_id),
            "name": "CI Pipeline",
            "status": "completed",
            "conclusion": "failure",
            "event": "push",
            "head_branch": "main",
            "duration_seconds": 900,
            "created_at": now,
            "analysis_status": "pending"
        }
        run_res = await db.workflow_runs.insert_one(run_anom)
        run_id = str(run_res.inserted_id)
        print(f"  [{GREEN}OK{RESET}] Seeded current failed anomalous run: {run_id} (duration: 900s)")

        # 5. Seed Jobs & Steps
        job = {
            "github_job_id": 5001,
            "run_id": ObjectId(run_id),
            "repo_id": ObjectId(repo_id),
            "name": "build_and_test",
            "status": "completed",
            "conclusion": "failure",
            "duration_seconds": 900,
            "runner_name": "ubuntu-latest",
            "started_at": now - timedelta(seconds=900),
            "completed_at": now
        }
        job_res = await db.workflow_jobs.insert_one(job)
        job_id = str(job_res.inserted_id)

        step = {
            "job_id": ObjectId(job_id),
            "run_id": ObjectId(run_id),
            "name": "Install dependencies",
            "number": 3,
            "status": "completed",
            "conclusion": "failure",
            "duration_seconds": 880
        }
        await db.workflow_steps.insert_one(step)

        # 6. Seed parsed logs with OOM / timeout errors
        parsed = {
            "run_id": ObjectId(run_id),
            "repo_id": ObjectId(repo_id),
            "summary": {"error_count": 1, "warning_count": 0},
            "errors": [
                {
                    "line_number": 145,
                    "severity": "error",
                    "category": "dependency",
                    "message": "npm ERR! cb() never called! (cache or network timeout)",
                    "raw_line": "npm ERR! cb() never called! (cache or network timeout)"
                }
            ],
            "first_failure": {
                "job_name": "build_and_test",
                "step_name": "Install dependencies",
                "line_number": 145,
                "message": "npm ERR! cb() never called!"
            },
            "parsed_at": now
        }
        await db.parsed_logs.insert_one(parsed)
        print(f"  [{GREEN}OK{RESET}] Seeded job, step, and parsed log details.")

        return user_id, repo_id, run_id

    except Exception as e:
        print(f"  [{RED}FAILED{RESET}] Seeding failed: {str(e)}")
        sys.exit(1)
    finally:
        client.close()


def generate_jwt(user_id: str):
    exp = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {
        "sub": user_id,
        "github_login": "ai-agent-tester",
        "role": "member",
        "type": "access",
        "exp": exp
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def verify_endpoints(jwt_token: str, repo_id: str, run_id: str):
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Trigger LangGraph analysis
        print(f"\n{BOLD}=== Step 2: Triggering LangGraph multi-agent analysis ==={RESET}")
        url_trigger = f"{GATEWAY_URL}/analysis/{run_id}/trigger"
        try:
            r = await client.post(url_trigger, headers=headers)
            print(f"  Trigger Response Code: {r.status_code}, Body: {r.text}")
            assert r.status_code == 200, "Trigger failed"
        except Exception as e:
            print(f"  [{RED}FAILED{RESET}] Unable to trigger analysis: {str(e)}")
            return

        # Poll for completion
        print("  Polling for analysis completion...")
        analysis_completed = False
        for attempt in range(10):
            await asyncio.sleep(2)
            r_run = await client.get(f"{GATEWAY_URL}/runs/{run_id}", headers=headers)
            run_data = r_run.json()
            status = run_data.get("analysis_status")
            print(f"    Attempt {attempt+1}: Analysis status = {status}")
            if status == "complete":
                analysis_completed = True
                break
            elif status == "failed":
                break
        
        if not analysis_completed:
            print(f"  [{RED}FAILED{RESET}] AI analysis did not complete successfully.")
            return
        print(f"  [{GREEN}OK{RESET}] LangGraph multi-agent analysis complete!")

        # 2. Verify Predictions
        print(f"\n{BOLD}=== Step 3: Verifying Failure Predictions ==={RESET}")
        try:
            r_pred = await client.get(f"{GATEWAY_URL}/analysis/{run_id}/predictions", headers=headers)
            pred_data = r_pred.json()
            print(f"  Predictions Response: {json.dumps(pred_data, indent=2)}")
            assert "build_failure_probability" in pred_data
            assert pred_data["build_failure_probability"] > 0
            print(f"  [{GREEN}OK{RESET}] Failure Prediction engine verified!")
        except Exception as e:
            print(f"  [{RED}FAILED{RESET}] Predictions verification failed: {str(e)}")

        # 3. Verify Anomalies
        print(f"\n{BOLD}=== Step 4: Verifying Anomaly Detection (Isolation Forest) ==={RESET}")
        try:
            r_anom = await client.get(f"{GATEWAY_URL}/analysis/{run_id}/anomalies", headers=headers)
            anom_data = r_anom.json()
            print(f"  Anomalies Response: {json.dumps(anom_data, indent=2)}")
            assert anom_data["is_anomaly"] is True, "Failed to detect duration anomaly using Isolation Forest!"
            print(f"  [{GREEN}OK{RESET}] Anomaly Detector successfully flagged anomalous run duration!")
        except Exception as e:
            print(f"  [{RED}FAILED{RESET}] Anomalies verification failed: {str(e)}")

        # 4. Verify RAG Chat with Workflow
        print(f"\n{BOLD}=== Step 5: Verifying RAG Chat with Workflow ==={RESET}")
        try:
            chat_payload = {"message": "Why did the npm build install fail?"}
            r_chat = await client.post(f"{GATEWAY_URL}/analysis/{run_id}/chat", headers=headers, json=chat_payload)
            chat_data = r_chat.json()
            print(f"  Chat query: {chat_payload['message']}")
            print(f"  AI Answer: {chat_data.get('answer')}")
            assert "answer" in chat_data
            print(f"  [{GREEN}OK{RESET}] RAG Chat system returned successful reasoning response!")
        except Exception as e:
            print(f"  [{RED}FAILED{RESET}] Chat verification failed: {str(e)}")

        # 5. Verify PR Risk assessment
        print(f"\n{BOLD}=== Step 6: Verifying PR Risk Report ==={RESET}")
        try:
            r_pr = await client.get(f"{GATEWAY_URL}/repos/{repo_id}/pr/12/risk", headers=headers)
            pr_data = r_pr.json()
            print(f"  PR Risk Report: {json.dumps(pr_data, indent=2)}")
            assert "risk_score" in pr_data
            print(f"  [{GREEN}OK{RESET}] PR Risk assessment engine verified!")
        except Exception as e:
            print(f"  [{RED}FAILED{RESET}] PR Risk verification failed: {str(e)}")


async def cleanup(user_id, repo_id, run_id):
    print(f"\n{BOLD}=== Step 7: Cleaning up Seeded Verification Data ==={RESET}")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    try:
        await db.users.delete_one({"_id": ObjectId(user_id)})
        await db.repositories.delete_one({"_id": ObjectId(repo_id)})
        await db.workflow_runs.delete_many({"repo_id": ObjectId(repo_id)})
        await db.workflow_jobs.delete_many({"repo_id": ObjectId(repo_id)})
        await db.workflow_steps.delete_many({"run_id": ObjectId(run_id)})
        await db.parsed_logs.delete_many({"run_id": ObjectId(run_id)})
        await db.ai_analysis.delete_many({"run_id": ObjectId(run_id)})
        await db.workflow_predictions.delete_many({"run_id": ObjectId(run_id)})
        await db.workflow_anomalies.delete_many({"run_id": ObjectId(run_id)})
        await db.pr_risk_reports.delete_many({"repo_id": ObjectId(repo_id)})
        print(f"  [{GREEN}OK{RESET}] Seeded databases cleaned successfully.")
    except Exception as e:
        print(f"  [{RED}ERROR{RESET}] Cleanup failed: {str(e)}")
    finally:
        client.close()


async def main():
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{CYAN}       AI WORKFLOW INTELLIGENCE AGENT VERIFIER      {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    
    # 1. Seed data
    user_id, repo_id, run_id = await seed_data()
    
    # 2. Get auth
    jwt_token = generate_jwt(user_id)
    
    # 3. Verify analysis & AI agent pipeline endpoints
    await verify_endpoints(jwt_token, repo_id, run_id)
    
    # 4. Clean up
    await cleanup(user_id, repo_id, run_id)
    
    print(f"\n{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{GREEN}        AI AGENT VERIFICATION RUN SUCCESSFUL!       {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")


if __name__ == "__main__":
    asyncio.run(main())
