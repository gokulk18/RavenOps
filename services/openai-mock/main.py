from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
import time
import uuid

app = FastAPI(title="RavenOps OpenAI Mock", version="1.0.0")

MOCK_ANALYSIS = {
    "executive_summary": "The CI pipeline failed due to a dependency resolution error in the build step. The npm registry returned a 404 for a pinned package version, blocking all downstream build and test steps. This is blocking deployments to production.",
    "root_cause": {
        "primary": "npm dependency resolution failure — pinned package version no longer available in registry",
        "category": "dependency",
        "confidence": 0.92,
        "evidence": [
            "npm ERR! 404 Not Found - package version not found",
            "Error: Cannot find module — module resolution failed",
            "Process completed with exit code 1"
        ]
    },
    "severity": {
        "level": "high",
        "reasoning": "Build failure blocks all merges to main branch and halts deployment pipeline"
    },
    "failure_chain": [
        "Workflow triggered on push to main branch",
        "Runner provisioned and checkout completed successfully",
        "npm ci command executed against package-lock.json",
        "npm attempted to fetch pinned package version from registry",
        "Registry returned HTTP 404 — version yanked or deprecated",
        "npm install exited with code 1",
        "Build step marked as failed",
        "Downstream test and deploy steps skipped",
        "Workflow concluded with failure conclusion"
    ],
    "suggested_fixes": [
        {
            "priority": 1,
            "action": "Update the dependency to the latest stable version and regenerate lock file",
            "code_or_config": "npm install <package>@latest && git add package.json package-lock.json && git commit -m 'fix: update dependency to latest stable version'",
            "effort": "minutes"
        },
        {
            "priority": 2,
            "action": "Add npm cache to GitHub Actions workflow to speed up subsequent runs",
            "code_or_config": "- uses: actions/setup-node@v4\n  with:\n    node-version: '20'\n    cache: 'npm'",
            "effort": "minutes"
        },
        {
            "priority": 3,
            "action": "Configure a private npm registry mirror for resilience against public registry outages",
            "code_or_config": "echo 'registry=https://your-private-registry.example.com' >> .npmrc",
            "effort": "hours"
        }
    ],
    "preventive_measures": [
        "Enable Dependabot or Renovate for automated dependency update PRs",
        "Use npm audit in CI pipeline to catch security vulnerabilities early",
        "Avoid pinning exact patch versions without a private registry mirror",
        "Add dependency caching to all CI workflows to reduce failure surface area",
        "Consider using a monorepo tool like Turborepo for better dependency management"
    ],
    "related_issues": [
        "npm ERR! 404 — common when package maintainer yanks a specific version",
        "GitHub Actions: actions/setup-node caching documentation",
        "Renovate bot auto-merge for minor/patch dependency updates"
    ],
    "is_flaky": False,
    "flaky_reasoning": None
}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "openai-mock", "version": "1.0.0"}


@app.post("/openai/deployments/{deployment}/chat/completions")
async def chat_completions(deployment: str, request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    user_message = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")

    response_text = json.dumps(MOCK_ANALYSIS)
    prompt_tokens = int(len(user_message.split()) * 1.3)
    completion_tokens = int(len(response_text.split()) * 1.3)

    return JSONResponse({
        "id": f"chatcmpl-mock-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": deployment,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens
        }
    })


# Also support the standard OpenAI endpoint format
@app.post("/v1/chat/completions")
async def chat_completions_v1(request: Request):
    return await chat_completions("gpt-4o", request)
