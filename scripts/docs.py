"""Serve the Quarto site. Make rebuilds résumé artifacts before calling this script."""

import os
import subprocess
import sys
from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]


def preview_site() -> None:
    port = int(os.environ.get("PORT", "4200"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    print(f"preview: http://localhost:{port}/", flush=True)
    subprocess.run(
        ["quarto", "preview", "--port", str(port)],
        check=True,
        cwd=ROOT_PATH,
        env={**os.environ, "QUARTO_PYTHON": sys.executable},
    )


if __name__ == "__main__":
    try:
        preview_site()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except KeyboardInterrupt:
        sys.exit(130)
