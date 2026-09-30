import os
import platform
import tempfile
from pathlib import Path


APP_NAME = "清华数据分析软件"
ORGANIZATION_NAME = "Tsinghua"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_project_root() -> Path:
    return PROJECT_ROOT


def get_bundled_root() -> Path:
    import sys

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return Path(meipass)
    return PROJECT_ROOT


def _qstandard_location(location_name: str) -> str:
    try:
        from PySide6.QtCore import QStandardPaths

        location = getattr(QStandardPaths.StandardLocation, location_name)
        return QStandardPaths.writableLocation(location)
    except Exception:
        return ""


def _platform_user_base(kind: str) -> Path:
    home = Path.home()
    system_name = platform.system()
    if system_name == "Darwin":
        if kind == "config":
            return home / "Library" / "Preferences"
        return home / "Library" / "Application Support"
    if system_name == "Windows":
        env_name = "APPDATA" if kind == "config" else "LOCALAPPDATA"
        return Path(os.environ.get(env_name, home / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME" if kind == "config" else "XDG_DATA_HOME", home / f".local/share"))


def _ensure_app_dir(path_text: str, kind: str) -> Path:
    base = Path(path_text).expanduser() if path_text else _platform_user_base(kind)
    if base.name != APP_NAME:
        base = base / APP_NAME
    return base.resolve(strict=False)


def get_user_config_dir() -> Path:
    override = os.environ.get("QH_DATA_ANALYSIS_CONFIG_DIR", "")
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return _ensure_app_dir(_qstandard_location("GenericConfigLocation"), "config")


def get_user_data_dir() -> Path:
    override = os.environ.get("QH_DATA_ANALYSIS_DATA_DIR", "")
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return _ensure_app_dir(_qstandard_location("GenericDataLocation"), "data")


def get_user_config_path() -> Path:
    return get_user_config_dir() / "app_config.json"


def get_user_run_log_path() -> Path:
    return get_user_data_dir() / "run_log.csv"


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-", delete=True):
            pass
        return True
    except OSError:
        return False


def prepare_runtime_environment():
    matplotlib_config_dir = get_user_data_dir() / "matplotlib"
    if not _is_writable_dir(matplotlib_config_dir):
        matplotlib_config_dir = Path(tempfile.gettempdir()) / "清华数据分析软件" / "matplotlib"
        if not _is_writable_dir(matplotlib_config_dir):
            matplotlib_config_dir = Path(tempfile.mkdtemp(prefix="清华数据分析软件-matplotlib-"))
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config_dir))
    return {"MPLCONFIGDIR": os.environ["MPLCONFIGDIR"]}


def get_project_config_path() -> Path:
    return PROJECT_ROOT / "config" / "app_config.json"


def get_project_default_config_path() -> Path:
    return PROJECT_ROOT / "config" / "default_config.json"


def get_project_run_log_path() -> Path:
    return PROJECT_ROOT / "outputs" / "run_log.csv"
