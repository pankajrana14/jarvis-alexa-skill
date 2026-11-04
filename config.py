"""Runtime configuration shared by the Lambda handler, wiki manager and wiki tools.

Jarvis runs either on a self-managed AWS Lambda (env vars set on the function) or as
an Alexa-hosted skill, where Lambda env vars cannot be edited. For the hosted case,
API keys ship in a `.env` file next to the code, and Alexa provides the S3 bucket via
S3_PERSISTENCE_BUCKET / S3_PERSISTENCE_REGION.
"""
import os
from pathlib import Path
from typing import Optional, Union

import boto3

# jarvis.env is what scripts/build_hosted.py bundles (a non-dot name, so the Alexa
# console's code editor shows and keeps it); .env is the local-dev file.
_DEFAULT_ENV_FILES = [Path(__file__).with_name("jarvis.env"), Path(__file__).with_name(".env")]


def load_bundled_env(env_file: Union[str, Path, None] = None) -> None:
    """Load KEY=value pairs from a bundled env file. Never overrides real env vars."""
    from dotenv import load_dotenv

    candidates = [Path(env_file)] if env_file else _DEFAULT_ENV_FILES
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)


def bucket_name(explicit: Optional[str] = None) -> str:
    name = explicit or os.environ.get("S3_BUCKET_NAME") or os.environ.get("S3_PERSISTENCE_BUCKET")
    if not name:
        raise RuntimeError("No S3 bucket configured: set S3_BUCKET_NAME (or run as an Alexa-hosted skill)")
    return name


def s3_client():
    region = os.environ.get("S3_PERSISTENCE_REGION")
    return boto3.client("s3", region_name=region) if region else boto3.client("s3")
