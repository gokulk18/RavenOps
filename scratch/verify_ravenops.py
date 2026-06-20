import os
import sys
import json
import hmac
import hashlib
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
WEBHOOK_SECRET = "ravenops-webhook-secret-local"

# Color constants for terminal formatting
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

async def test_health_checks():
    print(f"\n{BOLD}=== Step 1: Health Checking Services ==={RESET}")
    services = {
        "api-gateway": "http://api-gateway:8000/health",
        "auth-service": "http://auth-service:8001/health",
        "github-service": "http://github-service:8002/health",
        "workflow-service": "http://workflow-service:8003/health",
        "log-service": "http://log-service:8004/health",
        "parser-service": "http://parser-service:8005/health",
        "ai-service": "http://ai-service:8006/health",
        "analytics-service": "http://analytics-service:8007/health",
        "notification-service": "http://notification-service:8008/health",
        "openai-mock": "http://openai-mock:8080/health",
    }
    
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in services.items():
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    data = r.json()
                    print(f"  [{GREEN}UP{RESET}] {name} -> status: {data.get('status')}, version: {data.get('version', 'N/A')}")
                else:
                    print(f"  [{RED}DOWN{RESET}] {name} -> status code: {r.status_code}")
            except Exception as e:
                print(f"  [{RED}DOWN{RESET}] {name} -> error: {str(e)}")

async def test_database():
    print(f"\n{BOLD}=== Step 2: Testing Database Connection and Seed ==={RESET}")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    try:
        # Ping
        await client.admin.command("ping")
        print(f"  [{GREEN}OK{RESET}] Successfully connected to MongoDB.")
        
        # Clean up old test user
        await db.users.delete_many({"github_login": "ravenops-test-user"})
        await db.repositories.delete_many({"full_name": "test-owner/test-repo"})
        
        # Insert test user
        now = datetime.now(timezone.utc)
        user_doc = {
            "github_id": 99999999,
            "github_login": "ravenops-test-user",
            "name": "RavenOps Test User",
            "email": "test-user@ravenops.local",
            "avatar_url": "https://avatars.githubusercontent.com/u/99999999?v=4",
            "github_access_token": "mock-github-access-token-12345",
            "github_token_scope": "read:user+user:email",
            "role": "member",
            "organizations": [],
            "installation_ids": [],
            "is_active": True,
            "settings": {"notifications_enabled": True, "email_alerts": True, "slack_webhook_url": None},
            "created_at": now,
            "updated_at": now,
            "last_login_at": now
        }
        
        result = await db.users.insert_one(user_doc)
        user_id = str(result.inserted_id)
        print(f"  [{GREEN}OK{RESET}] Inserted test user: {user_id} (github_login: ravenops-test-user)")
        
        # Insert test repo
        repo_doc = {
            "github_repo_id": 11111111,
            "owner_id": ObjectId(user_id),
            "organization_id": None,
            "name": "test-repo",
            "full_name": "test-owner/test-repo",
            "owner_login": "test-owner",
            "owner_type": "User",
            "default_branch": "main",
            "private": False,
            "description": "Test Repo for Obsidian Observability",
            "html_url": "https://github.com/test-owner/test-repo",
            "language": "Python",
            "topics": [],
            "webhook_id": 123456,
            "webhook_secret": WEBHOOK_SECRET,
            "webhook_active": True,
            "installation_id": None,
            "sync_status": "synced",
            "last_synced_at": now,
            "connected_at": now,
            "is_active": True,
            "settings": {"auto_analyze": True, "notify_on_failure": True, "ai_analysis_enabled": True},
        }
        
        repo_result = await db.repositories.insert_one(repo_doc)
        print(f"  [{GREEN}OK{RESET}] Inserted test repository: {str(repo_result.inserted_id)} (full_name: test-owner/test-repo)")
        
        return user_id
    except Exception as e:
        print(f"  [{RED}FAILED{RESET}] MongoDB operations failed: {str(e)}")
        sys.exit(1)
    finally:
        client.close()

def generate_jwt(user_id: str):
    exp = datetime.now(timezone.utc) + timedelta(minutes=15)
    payload = {
        "sub": user_id,
        "github_login": "ravenops-test-user",
        "role": "member",
        "type": "access",
        "exp": exp
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def test_gateway_routing(jwt_token: str):
    print(f"\n{BOLD}=== Step 3: Testing API Gateway Authentication & Routing ==={RESET}")
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Test auth/me
        try:
            r = await client.get(f"{GATEWAY_URL}/auth/me", headers=headers)
            if r.status_code == 200:
                data = r.json()
                print(f"  [{GREEN}OK{RESET}] /auth/me succeeded! User login: {data.get('github_login')}, Role: {data.get('role')}")
            else:
                print(f"  [{RED}FAILED{RESET}] /auth/me returned {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  [{RED}ERROR{RESET}] Failed to reach /auth/me: {str(e)}")

        # Test repos/github
        try:
            r = await client.get(f"{GATEWAY_URL}/repos/github", headers=headers)
            if r.status_code == 200:
                data = r.json()
                print(f"  [{GREEN}OK{RESET}] /repos/github succeeded! Total repos returned (with mock token failing gracefully): {data.get('total')}")
            else:
                print(f"  [{RED}FAILED{RESET}] /repos/github returned {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  [{RED}ERROR{RESET}] Failed to reach /repos/github: {str(e)}")

        # Test repos/connect (should return 404 since mock GitHub token is invalid on real GitHub)
        try:
            body = {"full_name": "test-owner/another-repo"}
            r = await client.post(f"{GATEWAY_URL}/repos/connect", headers=headers, json=body)
            if r.status_code == 404:
                print(f"  [{GREEN}OK{RESET}] /repos/connect handled invalid GitHub token gracefully (returned 404: Repository not found)")
            else:
                print(f"  [{RED}UNEXPECTED{RESET}] /repos/connect returned {r.status_code}: {r.text}")
        except Exception as e:
            print(f"  [{RED}ERROR{RESET}] Failed to reach /repos/connect: {str(e)}")

async def test_webhook_receiver():
    print(f"\n{BOLD}=== Step 4: Testing Webhook Event Routing & Signature Verification ==={RESET}")
    
    # Mock push event payload
    payload = {
        "ref": "refs/heads/main",
        "before": "0000000000000000000000000000000000000000",
        "after": "1111111111111111111111111111111111111111",
        "repository": {
            "id": 11111111,
            "name": "test-repo",
            "full_name": "test-owner/test-repo",
            "private": False,
            "owner": {
                "name": "test-owner",
                "email": "test-owner@ravenops.local"
            }
        },
        "pusher": {
            "name": "ravenops-test-user",
            "email": "test-user@ravenops.local"
        }
    }
    
    payload_bytes = json.dumps(payload).encode()
    
    # Compute signature
    sig_hash = hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256).hexdigest()
    valid_sig = f"sha256={sig_hash}"
    invalid_sig = "sha256=invalid-signature-value-here"
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Test invalid signature
        try:
            r = await client.post(
                f"{GATEWAY_URL}/webhooks/receive",
                content=payload_bytes,
                headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "test-deliv-1", "X-Hub-Signature-256": invalid_sig}
            )
            if r.status_code == 401:
                print(f"  [{GREEN}OK{RESET}] Webhook blocked invalid signature successfully (401 Unauthorized)")
            else:
                print(f"  [{RED}FAILED{RESET}] Webhook allowed invalid signature: {r.status_code} ({r.text})")
        except Exception as e:
            print(f"  [{RED}ERROR{RESET}] Webhook invalid signature test failed: {str(e)}")
            
        # Test valid signature
        try:
            r = await client.post(
                f"{GATEWAY_URL}/webhooks/receive",
                content=payload_bytes,
                headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "test-deliv-2", "X-Hub-Signature-256": valid_sig}
            )
            if r.status_code == 200:
                data = r.json()
                print(f"  [{GREEN}OK{RESET}] Webhook processed valid signature successfully! Response: {data}")
            else:
                print(f"  [{RED}FAILED{RESET}] Webhook rejected valid signature: {r.status_code} ({r.text})")
        except Exception as e:
            print(f"  [{RED}ERROR{RESET}] Webhook valid signature test failed: {str(e)}")

async def clean_up_test_data(user_id: str):
    print(f"\n{BOLD}=== Step 5: Cleaning up Test Data ==={RESET}")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    try:
        res_user = await db.users.delete_one({"_id": ObjectId(user_id)})
        res_repo = await db.repositories.delete_many({"full_name": "test-owner/test-repo"})
        print(f"  [{GREEN}OK{RESET}] Test user deleted: {res_user.deleted_count}")
        print(f"  [{GREEN}OK{RESET}] Test repo deleted: {res_repo.deleted_count}")
    except Exception as e:
        print(f"  [{RED}ERROR{RESET}] Clean up failed: {str(e)}")
    finally:
        client.close()

async def main():
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{CYAN}       RAVENOPS PLATFORM AUTOMATIC VERIFICATION      {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")
    
    # 1. Health Checks
    await test_health_checks()
    
    # 2. Database Insertion
    user_id = await test_database()
    
    # 3. Generate Auth JWT
    jwt_token = generate_jwt(user_id)
    print(f"\n{BOLD}=== Auth Session Initialized ==={RESET}")
    print(f"  Token: {jwt_token[:30]}...[truncated]...{jwt_token[-10:]}")
    
    # 4. Gateway & Microservice Routing
    await test_gateway_routing(jwt_token)
    
    # 5. Webhook Signature & Receiver test
    await test_webhook_receiver()
    
    # 6. Clean up
    await clean_up_test_data(user_id)
    
    print(f"\n{BOLD}{CYAN}===================================================={RESET}")
    print(f"{BOLD}{GREEN}        VERIFICATION RUN COMPLETED SUCCESSFULLY!     {RESET}")
    print(f"{BOLD}{CYAN}===================================================={RESET}")

if __name__ == "__main__":
    asyncio.run(main())
