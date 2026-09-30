from pathlib import Path

from utils.runtime_paths import get_bundled_root


def resource_path(relative_path: str) -> str:
    rel = str(relative_path or "").strip().lstrip("/\\")
    return str((get_bundled_root() / rel).resolve(strict=False))


def resource_exists(relative_path: str) -> bool:
    return Path(resource_path(relative_path)).exists()
