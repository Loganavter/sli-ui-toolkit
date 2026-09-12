import sys
from pathlib import Path

def resource_path(relative_path: str) -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        base_path = Path(meipass)
    else:
        current_file = Path(__file__).resolve()
        base_path = current_file.parent.parent.parent

    return str(base_path / relative_path)

