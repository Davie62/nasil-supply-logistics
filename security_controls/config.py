"""Development-only random keys; production keys must come from secret storage."""
import os
from pathlib import Path


def local_key(root, name, generate):
    directory = Path(root) / ".local"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / name
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as output:
            output.write(generate())
    return path.read_text().strip()
