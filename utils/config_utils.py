import json
from pathlib import Path

from utils.resource_utils import resource_path
from utils.runtime_paths import get_project_config_path, get_user_config_path
from utils.date_range_utils import fill_process_dates
from utils.standard_paths import apply_standard_paths


DEFAULT_DATA_ROOT = ""
DEFAULT_CONFIG_TEMPLATE_PATH = Path(resource_path("config/default_config.json"))
CONFIG_PATH = get_user_config_path()
PROJECT_CONFIG_PATH = get_project_config_path()

_DEFAULT_CONFIG = {
    "software_name": "清华数据分析软件",
    "mode": "single_month",
    "data_root": "",
    "target_month": "",
    "process_start_date": "",
    "process_end_date": "",
    "report_file": "",
    "step0_output_file": "",
    "step0_auto_check_status": "",
    "step0_auto_check_message": "",
    "step0_auto_checked_at": "",
    "step0_review_status": "",
    "step0_review_message": "",
    "step0_reviewed_at": "",
    "step0_review_start_date": "",
    "step0_review_end_date": "",
    "history_lowfreq_file": "",
    "lowfreq_current_path": "",
    "lowfreq_result_file": "",
    "second_data_dir": "",
    "second_result_path": "",
    "abnormal_result_path": "",
    "step0_output_dir": "",
    "step1_output_dir": "",
    "step2_result_dir": "",
    "step2_abnormal_dir": "",
    "step3_result_dir": "",
    "manual_path_overrides": [],
    "step0_needs_rerun": False,
}

STEP0_REVIEW_INPUT_KEYS = {
    "target_month",
    "process_start_date",
    "process_end_date",
    "report_file",
}

STEP0_REVIEW_STATE_KEYS = (
    "step0_auto_check_status",
    "step0_auto_check_message",
    "step0_auto_checked_at",
    "step0_review_status",
    "step0_review_message",
    "step0_reviewed_at",
    "step0_review_start_date",
    "step0_review_end_date",
)


def get_config_path():
    return str(get_user_config_path())


def get_project_config_path_text():
    return str(PROJECT_CONFIG_PATH)


def get_default_config_path():
    return str(DEFAULT_CONFIG_TEMPLATE_PATH)


def load_json(path, default=None):
    file_path = Path(path)
    if not file_path.exists():
        return default if default is not None else {}
    with file_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_default_config():
    config = dict(_DEFAULT_CONFIG)
    template = load_json(DEFAULT_CONFIG_TEMPLATE_PATH, default={})
    if isinstance(template, dict):
        config.update(template)
    return fill_process_dates(config)


def _looks_like_user_config(config):
    if not isinstance(config, dict):
        return False
    path_keys = [
        "data_root",
        "report_file",
        "history_lowfreq_file",
        "lowfreq_current_path",
        "second_data_dir",
    ]
    return any(str(config.get(key, "") or "").strip() for key in path_keys)


def _initial_config_source():
    # Keeps compatibility with the old project-local app_config.json during development.
    legacy = load_json(PROJECT_CONFIG_PATH, default={})
    if _looks_like_user_config(legacy):
        return legacy
    return get_default_config()


def ensure_user_config_exists():
    user_path = get_user_config_path()
    if not user_path.exists():
        save_json(user_path, fill_process_dates(_initial_config_source()))
    return str(user_path)


def load_config():
    ensure_user_config_exists()
    config = get_default_config()
    config.update(load_json(get_user_config_path(), default={}))
    return apply_standard_paths(fill_process_dates(_normalize_default_values(config)))


def save_config(config: dict):
    merged = get_default_config()
    merged.update(config or {})
    merged = _normalize_default_values(merged)
    merged = apply_standard_paths(fill_process_dates(merged))
    save_json(get_user_config_path(), merged)
    return merged


def load_app_config(path=None):
    if path is None:
        return load_config()
    config = get_default_config()
    config.update(load_json(path, default={}))
    return apply_standard_paths(fill_process_dates(_normalize_default_values(config)))


def save_app_config(config, path=None):
    if path is None:
        return save_config(config)
    merged = get_default_config()
    merged.update(config or {})
    merged = _normalize_default_values(merged)
    merged = apply_standard_paths(fill_process_dates(merged))
    save_json(path, merged)
    return merged


def _normalize_default_values(config):
    normalized = dict(config or {})
    for key, default_value in _DEFAULT_CONFIG.items():
        if normalized.get(key) is None:
            normalized[key] = default_value
    return normalized


def invalidate_step0_review_if_inputs_changed(previous: dict, current: dict) -> tuple[dict, list[str]]:
    """Clear stale review metadata when the inputs that define step 0 change."""
    updated = dict(current or {})
    changed = [
        key
        for key in sorted(STEP0_REVIEW_INPUT_KEYS)
        if str((previous or {}).get(key, "") or "").strip()
        != str(updated.get(key, "") or "").strip()
    ]
    if not changed:
        return updated, []
    clear_step0_review_state(updated)
    updated["step0_needs_rerun"] = True
    return updated, changed


def clear_step0_review_state(config: dict) -> dict:
    """Clear automatic-check metadata and explicit human approval."""
    for key in STEP0_REVIEW_STATE_KEYS:
        config[key] = ""
    return config


def is_step0_review_approved(config: dict, start_date: str = "", end_date: str = "") -> bool:
    """Only an explicit, current-range human approval unlocks steps 1 to 3."""
    if str((config or {}).get("step0_review_status", "") or "").strip().lower() != "approved":
        return False
    if start_date and str((config or {}).get("step0_review_start_date", "") or "").strip() != start_date:
        return False
    if end_date and str((config or {}).get("step0_review_end_date", "") or "").strip() != end_date:
        return False
    return not bool((config or {}).get("step0_needs_rerun"))
