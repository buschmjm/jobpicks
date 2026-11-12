"""FastAPI application entrypoint."""

import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from api.mount import join_mount_path, mount_path_from_env
from api.routers import (
    admin,
    application_answers,
    auth,
    billing,
    career,
    config,
    deck,
    email,
    engagement,
    events,
    jobs,
    onboarding,
    pages,
    preferences,
    privacy,
    profile,
    referrals,
    resume,
    resume_chat,
    resume_variants,
    search,
    skills,
    titles,
    todo,
)
from api.routers.health import router as health_router
from api.routers.metrics import router as metrics_router
from api.routers.mobile import router as mobile_router
from api.routers.well_known import router as well_known_router
from api.schemas import HealthResponse

MOUNT_PATH = mount_path_from_env()
API_PREFIX = join_mount_path(MOUNT_PATH, "/api")
APP_PREFIX = MOUNT_PATH or ""

_LEGACY_SPA_ROUTE = re.compile(
    r"^(?:assets/)?(login|auth|onboarding|deck|search|settings|advisor|todo|application|applications|progress|privacy|terms|welcome)(?:/|$)"
)

app = FastAPI(
    title="Job Platform API",
    version="0.1.0",
    description="AI Job Discovery Platform — swipe deck + apply to-do",
)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://jobs.jbuschmann.com",
        "https://jobs-dev.jbuschmann.com",
        "https://app.willowriverautomation.com",
        "https://willowriverautomation.com",
        "https://auth.jbuschmann.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_API_ROUTERS = (
    auth.router,
    config.router,
    onboarding.router,
    preferences.router,
    profile.router,
    resume.router,
    resume_chat.router,
    resume_variants.router,
    career.router,
    skills.router,
    titles.router,
    deck.router,
    search.router,
    billing.router,
    mobile_router,
    email.router,
    referrals.router,
    todo.router,
    jobs.router,
    application_answers.router,
    events.router,
    engagement.router,
    privacy.router,
)

for router in _API_ROUTERS:
    app.include_router(router, prefix=API_PREFIX)

app.include_router(admin.router, prefix=APP_PREFIX)
app.include_router(pages.router, prefix=APP_PREFIX)
app.include_router(well_known_router)
app.include_router(health_router)
app.include_router(metrics_router)

_web_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
_has_frontend = _web_dist.is_dir()
_SPA_EXCLUDED_PREFIXES = (
    "api/",
    "admin",
    "privacy",
    "terms",
    "welcome",
    "health",
    "metrics",
    ".well-known/",
)


def _mount_relative_path(full_path: str) -> str:
    if not MOUNT_PATH:
        return full_path
    prefix = MOUNT_PATH.lstrip("/")
    if full_path == prefix:
        return ""
    if full_path.startswith(f"{prefix}/"):
        return full_path[len(prefix) + 1 :]
    return full_path


@app.get(join_mount_path(MOUNT_PATH, "/api/health"), response_model=HealthResponse)
async def api_health() -> HealthResponse:
    return HealthResponse()


@app.get(join_mount_path(MOUNT_PATH, "/api/hello"))
async def hello() -> dict[str, str]:
    """Deploy smoke test (works with or without built frontend)."""
    return {"message": "hello from job-platform"}


if MOUNT_PATH:

    @app.get("/api/{rest:path}")
    async def legacy_api_redirect(rest: str) -> RedirectResponse:
        return RedirectResponse(url=join_mount_path(MOUNT_PATH, f"/api/{rest}"), status_code=307)

    @app.get("/api")
    async def legacy_api_root_redirect() -> RedirectResponse:
        return RedirectResponse(url=join_mount_path(MOUNT_PATH, "/api"), status_code=307)


if _has_frontend:

    def _serve_spa_file(relative_path: str) -> FileResponse:
        if relative_path.startswith(_SPA_EXCLUDED_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        if relative_path:
            asset = _web_dist / relative_path
            if asset.is_file():
                return FileResponse(asset)
        index = _web_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built")

    if MOUNT_PATH:

        @app.get("/")
        async def root_redirect() -> RedirectResponse:
            return RedirectResponse(url=f"{MOUNT_PATH}/", status_code=307)

        @app.get(f"{MOUNT_PATH}")
        async def spa_mount_root() -> FileResponse:
            return _serve_spa_file("")

        @app.get(f"{MOUNT_PATH}/{{full_path:path}}")
        async def serve_spa_mounted(full_path: str = "") -> FileResponse:
            return _serve_spa_file(full_path)

        @app.get("/{full_path:path}", response_model=None)
        async def legacy_spa_redirect(full_path: str = "") -> RedirectResponse:
            if not full_path:
                return RedirectResponse(url=f"{MOUNT_PATH}/", status_code=307)
            if _LEGACY_SPA_ROUTE.match(full_path):
                return RedirectResponse(url=f"{MOUNT_PATH}/{full_path}", status_code=307)
            raise HTTPException(status_code=404, detail="Not Found")
    else:

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str = "") -> FileResponse:
            return _serve_spa_file(full_path)

else:

    @app.get("/")
    async def root_fallback() -> dict[str, str]:
        """Root when frontend is not built (local dev / CI)."""
        return {"message": "hello from job-platform"}


def main() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("APP_ENV", "development") == "development",
    )


if __name__ == "__main__":
    main()
