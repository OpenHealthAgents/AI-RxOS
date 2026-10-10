from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

command = sys.argv[1:]
prefix = os.environ.get("VALIDATION_PREFIX", "validation")
result = subprocess.run(command, capture_output=True, text=True, check=False)
Path(f"_{prefix}_stdout.txt").write_text(result.stdout, encoding="utf-8")
Path(f"_{prefix}_stderr.txt").write_text(result.stderr, encoding="utf-8")
Path(f"_{prefix}_exit.txt").write_text(str(result.returncode), encoding="utf-8")
Path(f"_{prefix}_result.json").write_text(
    json.dumps(
        {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(json.dumps({"returncode": result.returncode, "result_file": f"_{prefix}_result.json"}))
