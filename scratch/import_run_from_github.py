import os
import sys
import zipfile
import io
import gzip
import time
from datetime import datetime, timezone
import httpx
import pymongo
from bson import ObjectId
from azure.storage.blob import BlobServiceClient

# Configuration
MONGO_URI = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
DB_NAME = "ravenops"
AZURE_CONN_STR = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://azurite:10000/devstoreaccount1;"
CONTAINER_NAME = "ravenops-logs"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
RUN_ID = 27640485622
OWNER = "Googleeyy"
REPO = "ChapterOne-Frontend"

# Services endpoints (inside docker network)
PARSER_URL = "http://parser-service:8005"
AI_URL = "http://ai-service:8006"

def main():
    print("Connecting to MongoDB...")
    mongo_client = pymongo.MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    
    # 1. Fetch Repository details from GitHub
    print(f"Fetching repo details from GitHub: {OWNER}/{REPO}...")
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "RavenOps-Importer"
    }
    
    r_repo = httpx.get(f"https://api.github.com/repos/{OWNER}/{REPO}", headers=headers)
    if r_repo.status_code != 200:
        print(f"Error fetching repo: {r_repo.status_code} - {r_repo.text}")
        sys.exit(1)
    
    repo_data = r_repo.json()
    github_repo_id = repo_data["id"]
    
    # Check if repo exists in DB or insert
    user_doc = db.users.find_one({"github_login": "gokulk18"})
    user_id = user_doc["_id"] if user_doc else ObjectId()
    
    repo_doc = db.repositories.find_one({"github_repo_id": github_repo_id})
    if not repo_doc:
        repo_doc = {
            "github_repo_id": github_repo_id,
            "owner_id": user_id,
            "name": repo_data["name"],
            "full_name": repo_data["full_name"],
            "owner_login": repo_data["owner"]["login"],
            "owner_type": repo_data["owner"]["type"],
            "default_branch": repo_data.get("default_branch", "main"),
            "private": repo_data.get("private", False),
            "html_url": repo_data["html_url"],
            "is_active": True,
            "connected_at": datetime.now(timezone.utc)
        }
        repo_res = db.repositories.insert_one(repo_doc)
        repo_oid = repo_res.inserted_id
        print(f"Created repository in database: {repo_oid}")
    else:
        repo_oid = repo_doc["_id"]
        print(f"Found repository in database: {repo_oid}")
        
    # 2. Fetch Workflow Run details from GitHub
    print(f"Fetching workflow run details for run {RUN_ID}...")
    r_run = httpx.get(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{RUN_ID}", headers=headers)
    if r_run.status_code != 200:
        print(f"Error fetching run: {r_run.status_code} - {r_run.text}")
        sys.exit(1)
        
    run_data = r_run.json()
    
    started_at = datetime.fromisoformat(run_data["run_started_at"].replace("Z", "+00:00"))
    updated_at = datetime.fromisoformat(run_data["updated_at"].replace("Z", "+00:00"))
    created_at = datetime.fromisoformat(run_data["created_at"].replace("Z", "+00:00"))
    duration = int((updated_at - started_at).total_seconds()) if started_at and updated_at else None
    
    # Save/Update run in DB
    run_doc = db.workflow_runs.find_one({"github_run_id": RUN_ID})
    
    run_db_data = {
        "github_run_id": RUN_ID,
        "github_run_number": run_data.get("run_number"),
        "github_run_attempt": run_data.get("run_attempt", 1),
        "repo_id": repo_oid,
        "name": run_data.get("name", "Unknown Workflow"),
        "status": run_data.get("status", "queued"),
        "conclusion": run_data.get("conclusion"),
        "event": run_data.get("event", "push"),
        "head_branch": run_data.get("head_branch", ""),
        "head_sha": run_data.get("head_sha", ""),
        "head_commit": {
            "message": run_data.get("head_commit", {}).get("message", ""),
            "author": run_data.get("head_commit", {}).get("author", {}),
            "timestamp": run_data.get("head_commit", {}).get("timestamp"),
        },
        "triggering_actor": {
            "github_id": run_data.get("triggering_actor", {}).get("id"),
            "login": run_data.get("triggering_actor", {}).get("login", ""),
            "avatar_url": run_data.get("triggering_actor", {}).get("avatar_url", ""),
        },
        "run_started_at": started_at,
        "updated_at": datetime.now(timezone.utc),
        "html_url": run_data.get("html_url", ""),
        "duration_seconds": duration,
        "log_status": "stored",
        "analysis_status": "pending",
        "ai_analysis_id": None
    }
    
    if not run_doc:
        run_res = db.workflow_runs.insert_one({**run_db_data, "created_at": created_at})
        run_oid = run_res.inserted_id
        print(f"Created workflow run in database: {run_oid}")
    else:
        run_oid = run_doc["_id"]
        db.workflow_runs.update_one({"_id": run_oid}, {"$set": run_db_data})
        print(f"Updated workflow run in database: {run_oid}")

    # 3. Fetch Workflow Jobs and Steps from GitHub
    print(f"Fetching workflow jobs for run {RUN_ID}...")
    r_jobs = httpx.get(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{RUN_ID}/jobs", headers=headers)
    if r_jobs.status_code != 200:
        print(f"Error fetching jobs: {r_jobs.status_code} - {r_jobs.text}")
        sys.exit(1)
        
    jobs_data = r_jobs.json().get("jobs", [])
    
    for job in jobs_data:
        job_started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00")) if job.get("started_at") else None
        job_completed = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00")) if job.get("completed_at") else None
        job_dur = int((job_completed - job_started).total_seconds()) if job_started and job_completed else None
        
        job_db_doc = {
            "github_job_id": job.get("id"),
            "run_id": run_oid,
            "repo_id": repo_oid,
            "name": job.get("name", ""),
            "status": job.get("status", "queued"),
            "conclusion": job.get("conclusion"),
            "started_at": job_started,
            "completed_at": job_completed,
            "duration_seconds": job_dur,
            "runner_name": job.get("runner_name", ""),
            "runner_group_name": job.get("runner_group_name", ""),
            "labels": job.get("labels", []),
            "html_url": job.get("html_url", ""),
            "updated_at": datetime.now(timezone.utc)
        }
        
        job_res = db.workflow_jobs.find_one_and_update(
            {"github_job_id": job.get("id")},
            {"$set": job_db_doc, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
            upsert=True,
            return_document=pymongo.ReturnDocument.AFTER
        )
        job_oid = job_res["_id"]
        
        # Save steps
        for step in job.get("steps", []):
            step_started = datetime.fromisoformat(step["started_at"].replace("Z", "+00:00")) if step.get("started_at") else None
            step_completed = datetime.fromisoformat(step["completed_at"].replace("Z", "+00:00")) if step.get("completed_at") else None
            step_dur = int((step_completed - step_started).total_seconds()) if step_started and step_completed else None
            
            db.workflow_steps.update_one(
                {"job_id": job_oid, "number": step.get("number")},
                {"$set": {
                    "name": step.get("name", ""),
                    "number": step.get("number"),
                    "status": step.get("status", "queued"),
                    "conclusion": step.get("conclusion"),
                    "started_at": step_started,
                    "completed_at": step_completed,
                    "duration_seconds": step_dur,
                    "run_id": run_oid,
                    "repo_id": repo_oid,
                }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
                upsert=True
            )
            
    print("Stored jobs and steps successfully.")

    # 4. Download logs from GitHub
    print("Downloading logs zip from GitHub...")
    r_logs = httpx.get(f"https://api.github.com/repos/{OWNER}/{REPO}/actions/runs/{RUN_ID}/logs", headers=headers, follow_redirects=True)
    if r_logs.status_code != 200:
        print(f"Error downloading logs: {r_logs.status_code} - {r_logs.text}")
        sys.exit(1)
        
    print("Processing logs zip...")
    zip_bytes = r_logs.content
    log_lines = []
    
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        # Sort files alphabetically to keep steps inside jobs in order
        for file_path in sorted(z.namelist()):
            # Only process files, not directories, and skip metadata/root files if they aren't steps
            if file_path.endswith('.txt') and '/' in file_path:
                parts = file_path.split('/')
                job_name = parts[0]
                filename = parts[-1]
                # Extract step name from filename e.g. "3_npm ci.txt" -> "npm ci"
                step_name = filename.split('_', 1)[-1].rsplit('.', 1)[0] if '_' in filename else filename.rsplit('.', 1)[0]
                
                # Append step header to keep parser happy and format clean
                log_lines.append(f"##[group]Job: {job_name} | Step: {step_name}")
                
                content = z.read(file_path).decode('utf-8', errors='replace')
                for line in content.splitlines():
                    log_lines.append(line)
                
                log_lines.append("##[endgroup]")
                
    log_content = "\n".join(log_lines).encode("utf-8")
    compressed = gzip.compress(log_content)
    print(f"Logs processed: {len(log_lines)} lines, raw size: {len(log_content)} bytes, compressed: {len(compressed)} bytes.")

    # 5. Upload logs to Azurite
    blob_path = f"{OWNER}/{REPO}/{run_oid}/full_log.gz"
    print(f"Uploading logs to Azurite at {blob_path}...")
    blob_client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
    # Ensure container exists
    container_client = blob_client.get_container_client(CONTAINER_NAME)
    try:
        container_client.create_container()
    except Exception:
        pass
        
    b_client = blob_client.get_blob_client(CONTAINER_NAME, blob_path)
    b_client.upload_blob(compressed, overwrite=True)
    print("Uploaded logs successfully.")

    # Store logs metadata
    db.logs_metadata.update_one(
        {"run_id": run_oid},
        {"$set": {
            "run_id": run_oid,
            "repo_id": repo_oid,
            "status": "stored",
            "blob_container": CONTAINER_NAME,
            "blob_path": blob_path,
            "blob_url": f"azurite://{CONTAINER_NAME}/{blob_path}",
            "raw_size_bytes": len(log_content),
            "compressed_size_bytes": len(compressed),
            "compression_ratio": round(len(compressed) / len(log_content), 3),
            "line_count": len(log_lines),
            "stored_at": datetime.now(timezone.utc),
            "retention_policy": "hot",
            "error_message": None
        }, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    db.workflow_runs.update_one({"_id": run_oid}, {"$set": {"log_status": "stored"}})

    # 6. Trigger parsing
    print("Triggering log parsing on parser-service...")
    r_parse = httpx.post(f"{PARSER_URL}/parse/{run_oid}", timeout=30.0)
    print(f"Parser Trigger Status: {r_parse.status_code}, Response: {r_parse.text}")
    if r_parse.status_code != 200:
        sys.exit(1)
        
    # Poll for parser complete
    print("Waiting for parsing to complete...")
    for _ in range(15):
        run_check = db.workflow_runs.find_one({"_id": run_oid})
        status = run_check.get("analysis_status")
        print(f"  Status: {status}")
        if status == "parsed":
            break
        time.sleep(1)
        
    # 7. Trigger AI Analysis
    print("Triggering LangGraph analysis on ai-service...")
    r_ai = httpx.post(f"{AI_URL}/analysis/{run_oid}/trigger", timeout=60.0)
    print(f"AI Trigger Status: {r_ai.status_code}, Response: {r_ai.text}")
    if r_ai.status_code != 200:
        sys.exit(1)
        
    # Poll for AI complete
    print("Waiting for AI analysis to complete...")
    for _ in range(30):
        run_check = db.workflow_runs.find_one({"_id": run_oid})
        status = run_check.get("analysis_status")
        print(f"  Status: {status}")
        if status == "complete":
            break
        time.sleep(2)
        
    # Fetch and print analysis result
    analysis_doc = db.ai_analysis.find_one({"run_id": run_oid})
    if not analysis_doc:
        print("Error: AI analysis result not found in database.")
        sys.exit(1)
        
    print("\n" + "="*60)
    print("                 AI RUN ANALYSIS SUCCESSFUL!                ")
    print("="*60)
    print(f"Run ID: {RUN_ID}")
    print(f"Workflow: {run_db_data['name']} (Conclusion: {run_db_data['conclusion']})")
    print(f"Model Used: {analysis_doc.get('model_used')}")
    print(f"Executive Summary:\n{analysis_doc.get('executive_summary')}\n")
    print(f"Primary Root Cause:\nCategory: {analysis_doc.get('root_cause', {}).get('category')}")
    print(f"Primary: {analysis_doc.get('root_cause', {}).get('primary')}")
    print(f"Evidence:\n" + "\n".join([f"  - {e}" for e in analysis_doc.get('root_cause', {}).get('evidence', [])]))
    print("\nFailure Chain:")
    for step_num, step_desc in enumerate(analysis_doc.get('failure_chain', [])):
        print(f"  {step_num + 1}. {step_desc}")
    print("\nSuggested Fixes:")
    for fix in analysis_doc.get('suggested_fixes', []):
        print(f"  - [{fix.get('effort')}] {fix.get('action')}")
        if fix.get('code_or_config'):
            print(f"    Code/Config:\n{fix.get('code_or_config')}")
    print("="*60)

if __name__ == "__main__":
    main()
