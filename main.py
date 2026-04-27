from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# noinspection PyUnresolvedReferences
from PySide6.QtCore import QStandardPaths
# noinspection PyUnresolvedReferences
from PySide6.QtGui import QFont
# noinspection PyUnresolvedReferences
from PySide6.QtWidgets import QApplication, QMessageBox

from app.config import APP_NAME, APP_ORG, LOCK_STALE_MS, LOG_KEEP_DAYS, font_candidates
from app.ui.main_window import MainWindow
from app.ui.splash import SplashScreen


BASE_DIR = Path(__file__).resolve().parent


def app_data_dir() -> Path:
    path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not path:
        data_dir = BASE_DIR / "data"
    else:
        base = Path(path)
        data_dir = base if base.name.lower() == APP_ORG.lower() else (base / APP_ORG)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


DATA_DIR = app_data_dir()
LOG_DIR = DATA_DIR / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = datetime.now() - timedelta(days=LOG_KEEP_DAYS)
    for old_file in LOG_DIR.glob("*.log"):
        try:
            if datetime.fromtimestamp(old_file.stat().st_mtime) < cutoff:
                old_file.unlink(missing_ok=True)
        except Exception:
            pass
    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )


def get_or_create_app() -> QApplication:
    app = QApplication.instance()
    if app:
        return app
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    return app


def setup_fonts(app: QApplication) -> None:
    families = set(app.fontDatabase().families()) if hasattr(app, "fontDatabase") else set()
    family = next((name for name in font_candidates() if name in families), font_candidates()[-1])
    font = QFont(family, 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    logging.info("Font selected: %s", family)


class LockManager:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "app.lock"
        self._held = False

    def acquire(self) -> bool:
        payload = {"pid": os.getpid(), "created_at": time.time()}
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            self._held = True
            return True
        except FileExistsError:
            if self._is_stale():
                if self._force_remove():
                    return self.acquire()
            return False

    def release(self) -> None:
        try:
            if self._held and self.path.exists():
                self.path.unlink(missing_ok=True)
        except Exception:
            logging.exception("Failed to release lock file: %s", self.path)
        finally:
            self._held = False

    def _is_stale(self) -> bool:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            created_at = float(data.get("created_at", 0))
        except Exception:
            created_at = 0
        return (time.time() - created_at) * 1000 >= LOCK_STALE_MS

    def _force_remove(self) -> bool:
        try:
            self.path.unlink(missing_ok=True)
            return True
        except Exception:
            logging.exception("Failed to remove stale lock: %s", self.path)
            return False

    def __del__(self):
        self.release()


class Bootstrap:
    def __init__(self) -> None:
        self.app = get_or_create_app()
        setup_fonts(self.app)
        self.lock_manager = LockManager(DATA_DIR)
        self.window: MainWindow | None = None
        self.splash: SplashScreen | None = None
        self._cleaned = False
        atexit.register(self.cleanup)

        if not self.lock_manager.acquire():
            QMessageBox.warning(
                None,
                f"{APP_NAME} 已在运行",
                "如果刚才异常退出，请先确认旧窗口已经彻底关闭。\n"
                "如果还是打不开，重启 PyCharm 或电脑后再试通常就能恢复。",
            )
            raise SystemExit(0)

        self.app.aboutToQuit.connect(self.cleanup)
        self.splash = SplashScreen(BASE_DIR, DATA_DIR)
        self.splash.finished.connect(self.on_ready)
        self.splash.failed.connect(self.on_failed)
        logging.info("Bootstrap initialized")

    def run(self) -> int:
        assert self.splash is not None
        self.splash.start()
        screen = self.app.primaryScreen().availableGeometry()
        self.splash.move(screen.center() - self.splash.rect().center())
        try:
            return self.app.exec()
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        self.lock_manager.release()
        logging.info("Bootstrap cleanup finished")

    def on_ready(self, store, engine) -> None:
        try:
            self.window = MainWindow(store, engine, BASE_DIR)
            self.window.show()
            if self.splash:
                self.splash.close()
            logging.info("Main window ready")
        except Exception as exc:
            logging.exception("Failed while creating main window")
            if self.splash:
                self.splash.close()
            QMessageBox.critical(None, "启动失败", f"主界面创建没有成功：\n{exc}")
            self.cleanup()
            self.app.quit()

    def on_failed(self, message: str) -> None:
        try:
            if self.splash:
                self.splash.close()
            logging.error("Startup failed: %s", message)
            QMessageBox.critical(None, "启动失败", f"{APP_NAME} 启动失败：\n{message}")
        finally:
            self.cleanup()
            self.app.quit()


def excepthook(exc_type, exc_value, exc_traceback):
    logging.exception("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    app = QApplication.instance()
    if app:
        QMessageBox.critical(None, "程序异常", f"程序遇到了一个未处理的问题：\n{exc_value}")
    else:
        print(f"程序异常: {exc_value}", file=sys.stderr)


if __name__ == "__main__":
    setup_logging()
    sys.excepthook = excepthook
    raise SystemExit(Bootstrap().run())
