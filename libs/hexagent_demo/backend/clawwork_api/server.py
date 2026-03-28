"""Standalone uvicorn entry point for PyInstaller packaging."""

from __future__ import annotations

import os
import sys


def main() -> None:
    """Run the FastAPI app with uvicorn."""
    import uvicorn

    # When running as a PyInstaller bundle, ensure the bundled directory
    # is on sys.path so that relative imports resolve correctly.
    if getattr(sys, "frozen", False):
        bundle_dir = os.path.dirname(sys.executable)
        if bundle_dir not in sys.path:
            sys.path.insert(0, bundle_dir)

    from clawwork_api.main import app

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
