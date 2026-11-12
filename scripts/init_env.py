"""Create a local credential once; never print it or overwrite an existing file."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / ".env"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print(".env already exists; left unchanged")
else:
    with os.fdopen(fd, "w") as stream:
        stream.write(
            f"WREN_SERVICE_TOKEN={secrets.token_hex(32)}\n"
            "WREN_REGISTRY_PATH=models/registry.json\n"
            "WREN_PLAN_TIMEOUT_SECONDS=15\n"
            "WREN_STARTUP_TIMEOUT_SECONDS=60\n"
            "WREN_MAX_CONCURRENT_PLANS=3\n"
        )
    print("Created .env with a random service token (mode 0600)")
