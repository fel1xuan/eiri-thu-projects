from pathlib import Path

import pandas as pd


def read_excel_file(path, **kwargs):
    return pd.read_excel(Path(path).expanduser(), **kwargs)


def write_excel_file(df, path, index=False, **kwargs):
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=index, **kwargs)
    return str(output_path)


def list_excel_files(folder):
    folder_path = Path(folder).expanduser()
    if not folder_path.exists():
        return []
    return sorted(
        [
            path
            for path in folder_path.iterdir()
            if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"}
        ],
        key=lambda path: path.name,
    )
