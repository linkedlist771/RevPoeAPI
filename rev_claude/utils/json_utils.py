from pathlib import Path
from typing import List, Union, Dict
import json


def save_json(path: Path, data: Union[Dict, List]):
    with path.open("w") as f:
        json.dump(data, f, indent=4)


def load_json(path: Path) -> Union[Dict, List]:
    with path.open("r") as f:
        return json.load(f)
