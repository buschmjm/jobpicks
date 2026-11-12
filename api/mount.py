"""Shared app mount path helpers (e.g. /jobpicks on app.willowriverautomation.com)."""

from __future__ import annotations

import os


def normalize_mount_path(path: str | None) -> str:
    raw = (path or "").strip()
    if not raw or raw == "/":
        return ""
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/")


def mount_path_from_env() -> str:
    return normalize_mount_path(os.environ.get("APP_MOUNT_PATH"))


def join_mount_path(mount: str, suffix: str) -> str:
    suffix = suffix if suffix.startswith("/") else f"/{suffix}"
    return f"{mount}{suffix}" if mount else suffix
