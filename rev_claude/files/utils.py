from pathlib import Path


def get_file_name(file_path: str) -> str:
    return Path(file_path).name
