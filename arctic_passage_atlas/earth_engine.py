from __future__ import annotations

import os

from .environment import load_dotenv


def initialize_earth_engine():
    try:
        import ee
    except ImportError as exc:
        raise RuntimeError("Install the project first: python -m pip install -e .") from exc

    from pathlib import Path

    load_dotenv(Path.cwd())
    project = os.environ.get("EE_PROJECT_ID")
    if not project:
        raise RuntimeError(
            "EE_PROJECT_ID is not set. Copy .env.example to .env, register that Cloud project "
            "for Earth Engine, and run `earthengine authenticate` once."
        )
    try:
        ee.Initialize(project=project)
    except Exception as exc:
        raise RuntimeError(
            "Earth Engine initialization failed. Confirm the project is registered, then run "
            "`earthengine authenticate` and retry."
        ) from exc
    return ee

