import csv
import shutil
import traceback
from datetime import datetime
from pathlib import Path

from utils.runtime_paths import get_project_run_log_path, get_user_data_dir, get_user_run_log_path


RUN_LOG_PATH = get_user_run_log_path()
LEGACY_RUN_LOG_PATH = get_project_run_log_path()


def format_exception(exc):
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def append_text_log(log_path, message, level="INFO"):
    if not log_path:
        return []
    level_text = str(level or "INFO").upper()
    if level_text not in {"INFO", "SUCCESS", "WARNING", "ERROR"}:
        level_text = "INFO"
    file_path = Path(log_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_lines = str(message).splitlines() or [""]
    formatted_lines = [f"[{timestamp}] [{level_text}] {line}" for line in message_lines]
    with file_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(formatted_lines) + "\n")
    return formatted_lines


def create_pipeline_detail_log(started_at=None):
    """Create a per-run text log for the complete pipeline technical output."""
    timestamp = (started_at or datetime.now()).strftime("%Y%m%d_%H%M%S")
    log_dir = get_user_data_dir() / "detailed_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"pipeline_{timestamp}.log"
    path.touch(exist_ok=True)
    return str(path)


def get_run_log_path():
    return str(get_user_run_log_path())


def _resolve_log_path(log_path=None):
    return Path(log_path) if log_path else get_user_run_log_path()


def _copy_legacy_log_if_needed(path: Path):
    if path.exists():
        return
    legacy = LEGACY_RUN_LOG_PATH
    if legacy.exists() and legacy.stat().st_size > 0 and legacy.resolve(strict=False) != path.resolve(strict=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy, path)


def ensure_run_log(log_path=None):
    path = _resolve_log_path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if log_path is None:
        _copy_legacy_log_if_needed(path)
    if not path.exists() or path.stat().st_size == 0:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["time", "module", "status", "message"])
    return str(path)


def read_run_logs(log_path=None):
    path = Path(ensure_run_log(log_path)) if log_path is None else _resolve_log_path(log_path)
    if not path.exists() or path.stat().st_size == 0:
        return []

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append(
                {
                    "time": row.get("time", ""),
                    "module": row.get("module", ""),
                    "status": row.get("status", ""),
                    "message": row.get("message", ""),
                }
            )
    return list(reversed(rows))


def append_run_log(module: str, status: str, message: str, log_path=None, time_text=None):
    path = Path(ensure_run_log(log_path))
    timestamp = time_text or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status_text = str(status or "").strip().lower()
    if status_text not in {"success", "failed", "skipped", "warning"}:
        status_text = "skipped"
    message_text = " ".join(str(message or "").split())
    if len(message_text) > 500:
        message_text = message_text[:497] + "..."
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, module, status_text, message_text])
    return str(path)
