import time
import uuid
import hashlib
import hmac
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import redis.asyncio as aioredis
import jwt as pyjwt
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    redis_url: str = "redis://:ravenops_redis@redis:6379/0"
    jwt_secret: str = "super-secret-jwt-key-change-in-production-min-32-chars"
    jwt_algorithm: str = "HS256"
    github_webhook_secret: str = "ravenops-webhook-secret-local"
    auth_service_url: str = "http://auth-service:8001"
    github_service_url: str = "http://github-service:8002"
    workflow_service_url: str = "http://workflow-service:8003"
    log_service_url: str = "http://log-service:8004"
    parser_service_url: str = "http://parser-service:8005"
    ai_service_url: str = "http://ai-service:8006"
    analytics_service_url: str = "http://analytics-service:8007"
    notification_service_url: str = "http://notification-service:8008"
    rate_limit_user: int = 100
    rate_limit_org: int = 1000
    environment: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
redis_client: Optional[aioredis.Redis] = None
http_client: Optional[httpx.AsyncClient] = None
logger = structlog.get_logger()

ROUTE_MAP = {
    "/auth": settings.auth_service_url,
    "/repos": settings.github_service_url,
    "/organizations": settings.github_service_url,
    "/webhooks": settings.github_service_url,
    "/github-app": settings.github_service_url,
    "/rate-limit": settings.github_service_url,
    "/workflows": settings.workflow_service_url,
    "/runs": settings.workflow_service_url,
    "/logs": settings.log_service_url,
    "/analysis": settings.ai_service_url,
    "/analytics": settings.analytics_service_url,
    "/notifications": settings.notification_service_url,
}

PUBLIC_PREFIXES = [
    "/health", "/docs", "/openapi.json",
    "/auth/github/oauth/authorize",
    "/auth/github/oauth/callback",
    "/auth/github/app/callback",
    "/auth/refresh",
    "/auth/logout",
    "/webhooks/receive",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=5.0),
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50)
    )
    logger.info("API Gateway started", env=settings.environment)
    yield
    if redis_client:
        await redis_client.aclose()
    if http_client:
        await http_client.aclose()


app = FastAPI(title="RavenOps API Gateway", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


async def sliding_window_rate_limit(key: str, limit: int) -> tuple[bool, int, int]:
    now = int(time.time())
    window = 60
    redis_key = f"ratelimit:{key}"
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(redis_key, 0, now - window)
    pipe.zadd(redis_key, {str(uuid.uuid4()): now})
    pipe.zcard(redis_key)
    pipe.expire(redis_key, window)
    results = await pipe.execute()
    count = results[2]
    return count <= limit, max(0, limit - count), now + window


def verify_webhook_sig(payload: bytes, sig: str) -> bool:
    expected = hmac.new(settings.github_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", sig)


def is_public(path: str) -> bool:
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def get_downstream(path: str) -> Optional[str]:
    for prefix, url in ROUTE_MAP.items():
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            return url + path
    return None


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway", "version": "1.0.0"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    full_path = f"/{path}"
    request_id = str(uuid.uuid4())

    # Webhook: verify signature, skip JWT
    if full_path.startswith("/webhooks/receive"):
        body = await request.body()
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not verify_webhook_sig(body, sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        downstream = settings.github_service_url + full_path
        fwd_headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
        fwd_headers["X-Request-Id"] = request_id
        try:
            resp = await http_client.request(request.method, downstream, content=body, headers=fwd_headers)
            return Response(content=resp.content, status_code=resp.status_code)
        except Exception as e:
            raise HTTPException(status_code=503, detail="Webhook handler unavailable")

    user_id = None
    user_role = "viewer"
    remaining = settings.rate_limit_user

    if not is_public(full_path):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization token")
        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            user_id = payload.get("sub")
            user_role = payload.get("role", "viewer")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        allowed, remaining, reset_ts = await sliding_window_rate_limit(f"user:{user_id}", settings.rate_limit_user)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in a moment."},
                headers={
                    "X-RateLimit-Limit": str(settings.rate_limit_user),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ts),
                    "Retry-After": str(reset_ts - int(time.time())),
                },
            )

    downstream_url = get_downstream(full_path)
    if not downstream_url:
        raise HTTPException(status_code=404, detail=f"No route for: {full_path}")

    body = await request.body()
    fwd_headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    fwd_headers["X-Request-Id"] = request_id
    if user_id:
        fwd_headers["X-User-Id"] = user_id
        fwd_headers["X-User-Role"] = user_role

    try:
        resp = await http_client.request(
            method=request.method,
            url=downstream_url,
            content=body,
            headers=fwd_headers,
            params=dict(request.query_params),
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Downstream service unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Downstream service timeout")

    resp_headers = {
        "X-Request-Id": request_id,
        "X-RateLimit-Limit": str(settings.rate_limit_user),
        "X-RateLimit-Remaining": str(remaining),
    }
    if ct := resp.headers.get("content-type"):
        resp_headers["content-type"] = ct

    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
