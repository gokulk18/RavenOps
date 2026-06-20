import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
from pydantic_settings import BaseSettings
from typing import Optional
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
import jwt as pyjwt
import httpx


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://ravenops:ravenops_pass@mongodb:27017/ravenops?authSource=admin"
    mongodb_db_name: str = "ravenops"
    redis_url: str = "redis://:ravenops_redis@redis:6379/0"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:3000/auth/callback"
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = "ravenops-webhook-secret-local"
    jwt_secret: str = "super-secret-jwt-key-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
mongo_client: Optional[AsyncIOMotorClient] = None
db = None
redis_client: Optional[aioredis.Redis] = None
logger = structlog.get_logger()

GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db, redis_client
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client[settings.mongodb_db_name]
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Auth service started", env=settings.environment)
    yield
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.aclose()


app = FastAPI(title="RavenOps Auth Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── JWT helpers ───────────────────────────────────────────────────────
def create_access_token(user_id: str, login: str, role: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return pyjwt.encode(
        {"sub": user_id, "github_login": login, "role": role, "type": "access", "exp": exp},
        settings.jwt_secret, algorithm=settings.jwt_algorithm
    )


def create_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_token(token: str) -> dict:
    return pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def refresh_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)


def require_auth(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    try:
        return decode_token(header[7:])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── GitHub OAuth ──────────────────────────────────────────────────────
async def gh_get(path: str, token: str) -> Optional[dict | list]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{GITHUB_API_URL}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        return r.json() if r.status_code == 200 else None


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-service", "version": "1.0.0"}


@app.get("/auth/github/oauth/authorize")
async def oauth_authorize():
    state = secrets.token_urlsafe(32)
    if redis_client:
        await redis_client.setex(f"oauth_state:{state}", 600, "valid")
    params = (
        f"client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_redirect_uri}"
        f"&scope=read:user+user:email"
        f"&state={state}"
    )
    return {"authorization_url": f"https://github.com/login/oauth/authorize?{params}", "state": state}


@app.post("/auth/github/oauth/callback")
async def oauth_callback(request: Request, body: dict):
    from bson import ObjectId
    code = body.get("code")
    state = body.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    if state and redis_client:
        if not await redis_client.get(f"oauth_state:{state}"):
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
        await redis_client.delete(f"oauth_state:{state}")

    # Exchange code
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            GITHUB_TOKEN_URL,
            data={"client_id": settings.github_client_id, "client_secret": settings.github_client_secret,
                  "code": code, "redirect_uri": settings.github_redirect_uri},
            headers={"Accept": "application/json"},
        )
    token_data = r.json()
    if "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="GitHub token exchange failed")

    gh_token = token_data["access_token"]
    gh_user = await gh_get("/user", gh_token)
    if not gh_user:
        raise HTTPException(status_code=400, detail="Failed to fetch GitHub user")

    email = gh_user.get("email")
    if not email:
        emails = await gh_get("/user/emails", gh_token) or []
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        if primary:
            email = primary["email"]

    now = datetime.now(timezone.utc)
    existing = await db.users.find_one({"github_id": gh_user["id"]})
    if existing:
        await db.users.update_one(
            {"github_id": gh_user["id"]},
            {"$set": {"github_access_token": gh_token, "last_login_at": now, "updated_at": now,
                      "name": gh_user.get("name") or gh_user["login"],
                      "avatar_url": gh_user.get("avatar_url"), "email": email}}
        )
        user_id = str(existing["_id"])
        role = existing.get("role", "member")
    else:
        doc = {
            "github_id": gh_user["id"], "github_login": gh_user["login"],
            "name": gh_user.get("name") or gh_user["login"], "email": email,
            "avatar_url": gh_user.get("avatar_url"), "github_access_token": gh_token,
            "github_token_scope": token_data.get("scope", ""), "role": "member",
            "organizations": [], "installation_ids": [], "is_active": True,
            "settings": {"notifications_enabled": True, "email_alerts": True, "slack_webhook_url": None},
            "created_at": now, "updated_at": now, "last_login_at": now
        }
        result = await db.users.insert_one(doc)
        user_id = str(result.inserted_id)
        role = "member"

    access_token = create_access_token(user_id, gh_user["login"], role)
    raw_refresh, hashed_refresh = create_refresh_token()
    await db.refresh_tokens.insert_one({
        "user_id": ObjectId(user_id), "token_hash": hashed_refresh,
        "device_info": request.headers.get("User-Agent", "unknown"),
        "ip_address": request.client.host if request.client else "unknown",
        "expires_at": refresh_expiry(), "revoked_at": None, "created_at": now
    })
    await db.audit_logs.insert_one({
        "user_id": ObjectId(user_id), "action": "login", "resource": "auth",
        "details": {"method": "github_oauth"},
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("User-Agent", ""), "timestamp": now
    })

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    return {
        "access_token": access_token, "refresh_token": raw_refresh,
        "token_type": "bearer", "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": _serialize_user(user)
    }


@app.post("/auth/refresh")
async def refresh(body: dict):
    from bson import ObjectId
    raw = body.get("refresh_token")
    if not raw:
        raise HTTPException(status_code=400, detail="Missing refresh_token")
    token_doc = await db.refresh_tokens.find_one({"token_hash": hash_token(raw), "revoked_at": None})
    if not token_doc:
        raise HTTPException(status_code=401, detail="Invalid or revoked refresh token")
    now = datetime.now(timezone.utc)
    if token_doc["expires_at"].replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    user = await db.users.find_one({"_id": token_doc["user_id"]})
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="User inactive")
    await db.refresh_tokens.update_one({"_id": token_doc["_id"]}, {"$set": {"revoked_at": now}})
    new_raw, new_hashed = create_refresh_token()
    await db.refresh_tokens.insert_one({
        "user_id": token_doc["user_id"], "token_hash": new_hashed,
        "device_info": token_doc.get("device_info", ""), "ip_address": token_doc.get("ip_address", ""),
        "expires_at": refresh_expiry(), "revoked_at": None, "created_at": now
    })
    user_id = str(user["_id"])
    return {
        "access_token": create_access_token(user_id, user["github_login"], user.get("role", "member")),
        "refresh_token": new_raw, "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60
    }


@app.post("/auth/logout")
async def logout(body: dict):
    raw = body.get("refresh_token")
    if raw:
        await db.refresh_tokens.update_one(
            {"token_hash": hash_token(raw)},
            {"$set": {"revoked_at": datetime.now(timezone.utc)}}
        )
    return {"message": "Logged out successfully"}


@app.get("/auth/me")
async def get_me(request: Request):
    from bson import ObjectId
    payload = require_auth(request)
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _serialize_user(user)


@app.put("/auth/me")
async def update_me(request: Request, body: dict):
    from bson import ObjectId
    payload = require_auth(request)
    fields = {}
    for k in ["name", "email", "settings"]:
        if k in body:
            fields[k] = body[k]
    fields["updated_at"] = datetime.now(timezone.utc)
    await db.users.update_one({"_id": ObjectId(payload["sub"])}, {"$set": fields})
    return {"message": "Profile updated"}


@app.get("/auth/organizations")
async def list_orgs(request: Request):
    from bson import ObjectId
    payload = require_auth(request)
    user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    orgs = []
    async for org in db.organizations.find({"_id": {"$in": user.get("organizations", [])}}):
        orgs.append(_serialize_org(org))
    return {"organizations": orgs, "total": len(orgs)}


@app.post("/auth/organizations/{org_id}/invite")
async def invite_user(org_id: str, request: Request, body: dict):
    from bson import ObjectId
    payload = require_auth(request)
    if payload.get("role") not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    login = body.get("github_login")
    role = body.get("role", "member")
    if not login:
        raise HTTPException(status_code=400, detail="github_login required")
    org = await db.organizations.find_one({"_id": ObjectId(org_id)})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    invitee = await db.users.find_one({"github_login": login})
    if not invitee:
        raise HTTPException(status_code=404, detail=f"User '{login}' not found")
    existing = any(m["user_id"] == invitee["_id"] for m in org.get("members", []))
    if existing:
        raise HTTPException(status_code=409, detail="Already a member")
    now = datetime.now(timezone.utc)
    await db.organizations.update_one(
        {"_id": ObjectId(org_id)},
        {"$push": {"members": {"user_id": invitee["_id"], "role": role, "joined_at": now}}}
    )
    await db.users.update_one({"_id": invitee["_id"]}, {"$addToSet": {"organizations": ObjectId(org_id)}})
    return {"message": f"User '{login}' invited"}


@app.delete("/auth/organizations/{org_id}/members/{uid}")
async def remove_member(org_id: str, uid: str, request: Request):
    from bson import ObjectId
    payload = require_auth(request)
    if payload.get("role") not in ["owner", "admin"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    await db.organizations.update_one(
        {"_id": ObjectId(org_id)}, {"$pull": {"members": {"user_id": ObjectId(uid)}}}
    )
    await db.users.update_one({"_id": ObjectId(uid)}, {"$pull": {"organizations": ObjectId(org_id)}})
    return {"message": "Member removed"}


# ── Serializers ───────────────────────────────────────────────────────
def _serialize_user(u: dict) -> dict:
    return {
        "id": str(u["_id"]), "github_id": u["github_id"], "github_login": u["github_login"],
        "name": u["name"], "email": u.get("email"), "avatar_url": u.get("avatar_url"),
        "role": u.get("role", "member"),
        "organizations": [str(o) for o in u.get("organizations", [])],
        "settings": u.get("settings", {}), "last_login_at": u.get("last_login_at"),
        "created_at": u["created_at"], "is_active": u.get("is_active", True)
    }


def _serialize_org(o: dict) -> dict:
    return {
        "id": str(o["_id"]), "github_org_id": o["github_org_id"], "name": o["name"],
        "slug": o["slug"], "avatar_url": o.get("avatar_url"), "plan": o.get("plan", "free"),
        "owner_id": str(o["owner_id"]),
        "members": [{"user_id": str(m["user_id"]), "role": m["role"], "joined_at": m["joined_at"]}
                    for m in o.get("members", [])],
        "created_at": o["created_at"]
    }
