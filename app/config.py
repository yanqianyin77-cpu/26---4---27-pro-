from __future__ import annotations

import platform


APP_NAME = "Kotoba Note"
APP_ORG = "KotobaNote"
LOCK_STALE_MS = 30_000
LOG_KEEP_DAYS = 14
SPLASH_TIMEOUT_MS = 20_000


def font_candidates() -> list[str]:
    system = platform.system().lower()
    if system == "windows":
        return ["Microsoft YaHei UI", "Microsoft YaHei", "Yu Gothic UI", "Segoe UI", "Arial"]
    if system == "darwin":
        return ["PingFang SC", "Hiragino Sans GB", "Hiragino Sans", "Helvetica Neue", "Arial"]
    return ["Noto Sans CJK SC", "Noto Sans CJK JP", "Source Han Sans SC", "DejaVu Sans", "Sans Serif"]
