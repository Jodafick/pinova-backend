"""One-shot script to reorganize fotoce_backend module layout."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "fotoce_backend"

MOVES: dict[str, str] = {
    "cache_config.py": "config/cache.py",
    "exceptions.py": "core/exceptions.py",
    "request_context.py": "core/request_context.py",
    "checks.py": "core/checks.py",
    "security_middleware.py": "middleware/security.py",
    "media_middleware.py": "middleware/media.py",
    "sentry_middleware.py": "middleware/sentry.py",
    "unread_notifications_middleware.py": "middleware/unread_notifications.py",
    "media_access.py": "media_serving/access.py",
    "media_cache.py": "media_serving/cache.py",
    "media_views.py": "media_serving/views.py",
    "storage_backends.py": "media_serving/storage.py",
    "health_views.py": "health/views.py",
    "ws_auth.py": "websocket/auth.py",
    "ws_heartbeat.py": "websocket/heartbeat.py",
    "ws_ratelimit.py": "websocket/ratelimit.py",
    "json_logging.py": "observability/logging.py",
    "sentry_config.py": "observability/sentry.py",
    "otel.py": "observability/otel.py",
    "analytics.py": "observability/analytics.py",
    "throttling.py": "security/throttling.py",
    "ratelimit_helpers.py": "security/ratelimit_helpers.py",
    "permissions_audit.py": "security/permissions_audit.py",
    "resilience.py": "security/resilience.py",
}

IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    ("fotoce_backend.config.cache", "fotoce_backend.config.cache"),
    ("fotoce_backend.core.exceptions", "fotoce_backend.core.exceptions"),
    ("fotoce_backend.core.request_context", "fotoce_backend.core.request_context"),
    ("fotoce_backend.core.checks", "fotoce_backend.core.checks"),
    ("fotoce_backend.middleware.security", "fotoce_backend.middleware.security"),
    ("fotoce_backend.middleware.media", "fotoce_backend.middleware.media"),
    ("fotoce_backend.middleware.sentry", "fotoce_backend.middleware.sentry"),
    (
        "fotoce_backend.middleware.unread_notifications",
        "fotoce_backend.middleware.unread_notifications",
    ),
    ("fotoce_backend.media_serving.access", "fotoce_backend.media_serving.access"),
    ("fotoce_backend.media_serving.cache", "fotoce_backend.media_serving.cache"),
    ("fotoce_backend.media_serving.views", "fotoce_backend.media_serving.views"),
    ("fotoce_backend.media_serving.storage", "fotoce_backend.media_serving.storage"),
    ("fotoce_backend.health.views", "fotoce_backend.health.views"),
    ("fotoce_backend.websocket.auth", "fotoce_backend.websocket.auth"),
    ("fotoce_backend.websocket.heartbeat", "fotoce_backend.websocket.heartbeat"),
    ("fotoce_backend.websocket.ratelimit", "fotoce_backend.websocket.ratelimit"),
    ("fotoce_backend.observability.logging", "fotoce_backend.observability.logging"),
    ("fotoce_backend.observability.sentry", "fotoce_backend.observability.sentry"),
    ("fotoce_backend.observability.otel", "fotoce_backend.observability.otel"),
    ("fotoce_backend.observability.analytics", "fotoce_backend.observability.analytics"),
    ("fotoce_backend.security.throttling", "fotoce_backend.security.throttling"),
    ("fotoce_backend.security.ratelimit_helpers", "fotoce_backend.security.ratelimit_helpers"),
    ("fotoce_backend.security.permissions_audit", "fotoce_backend.security.permissions_audit"),
    ("fotoce_backend.security.resilience", "fotoce_backend.security.resilience"),
]

RELATIVE_FIXES: list[tuple[str, str]] = [
    ("from fotoce_backend.config.cache import", "from fotoce_backend.config.cache import"),
    ("from fotoce_backend.core import checks", "from fotoce_backend.core import checks"),
    ("from fotoce_backend.observability.sentry import", "from fotoce_backend.observability.sentry import"),
    ("from fotoce_backend.observability.otel import", "from fotoce_backend.observability.otel import"),
    ("from fotoce_backend.media_serving.access import", "from fotoce_backend.media_serving.access import"),
    ("from fotoce_backend.media_serving.views import", "from fotoce_backend.media_serving.views import"),
    ("from fotoce_backend.health.views import", "from fotoce_backend.health.views import"),
    ("from fotoce_backend.websocket.auth import", "from fotoce_backend.websocket.auth import"),
]


def ensure_packages() -> None:
    for dest in MOVES.values():
        (PKG / dest).parent.mkdir(parents=True, exist_ok=True)
        init = (PKG / dest).parent / "__init__.py"
        if not init.exists():
            init.write_text("", encoding="utf-8")
    tests_dir = PKG / "tests"
    tests_dir.mkdir(exist_ok=True)
    if not (tests_dir / "__init__.py").exists():
        (tests_dir / "__init__.py").write_text("", encoding="utf-8")


def move_files() -> None:
    ensure_packages()
    for src_name, dest_rel in MOVES.items():
        src = PKG / src_name
        dest = PKG / dest_rel
        if src.exists() and not dest.exists():
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            src.unlink()
    for test_file in PKG.glob("tests_*.py"):
        dest = PKG / "tests" / test_file.name
        if not dest.exists():
            dest.write_text(test_file.read_text(encoding="utf-8"), encoding="utf-8")
            test_file.unlink()


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in IMPORT_REPLACEMENTS:
        text = text.replace(old, new)
    for old, new in RELATIVE_FIXES:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def patch_tree(base: Path) -> int:
    skip = {".venv", "venv", "__pycache__", "staticfiles", "node_modules"}
    count = 0
    for path in base.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        if patch_file(path):
            count += 1
    return count


def main() -> None:
    move_files()
    patched = patch_tree(ROOT)
    print(f"Moved {len(MOVES)} modules + test files; patched {patched} Python files.")


if __name__ == "__main__":
    main()
