#!/usr/bin/env python3
"""
Build a zip for an Alexa-hosted skill: Alexa developer console -> Code tab -> Import Code.

Run from the jarvis/ directory: python scripts/build_hosted.py
Output: dist/alexa-hosted-code.zip (gitignored - it contains your API keys).

Alexa-hosted skills install requirements.txt themselves and can't have Lambda env
vars edited, so the zip holds the source plus a generated lambda/jarvis.env with the keys
copied from your local .env. S3_BUCKET_NAME is left out on purpose: the hosted skill
uses the bucket Alexa provides (S3_PERSISTENCE_BUCKET).
"""
import sys
import zipfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "alexa-hosted-code.zip"

SOURCE_FILES = [
    "lambda_function.py",
    "intent_handlers.py",
    "agent.py",
    "config.py",
    "wiki_manager.py",
    "ssml_builder.py",
    "requirements.txt",
]
HOSTED_ENV_KEYS_SKIP = {"S3_BUCKET_NAME"}


def hosted_env() -> str:
    values = dotenv_values(ROOT / ".env")
    if not values.get("LLM_MODEL"):
        sys.exit("Error: LLM_MODEL missing from .env")
    bad = [k for k, v in values.items() if not v or "PASTE_" in v]
    if bad:
        sys.exit(f"Error: fill in these .env values first: {', '.join(bad)}")
    lines = [f"{k}={v}" for k, v in values.items() if k not in HOSTED_ENV_KEYS_SKIP]
    return "\n".join(lines) + "\n"


def _add(zf: zipfile.ZipFile, arcname: str, text: str) -> None:
    """Add a text file as a Unix entry: LF line endings, mode 0644 (readable by the
    Lambda runtime user), regardless of the Windows file it came from."""
    info = zipfile.ZipInfo(arcname, date_time=(2026, 1, 1, 0, 0, 0))
    info.create_system = 3  # Unix, so the mode bits below are honoured
    info.external_attr = (0o100644 << 16)
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, text.replace("\r\n", "\n"))


def main():
    env_text = hosted_env()
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in SOURCE_FILES:
            _add(zf, f"lambda/{name}", (ROOT / name).read_text(encoding="utf-8"))
        for f in sorted((ROOT / "tools").glob("*.py")):
            _add(zf, f"lambda/tools/{f.name}", f.read_text(encoding="utf-8"))
        _add(zf, "lambda/jarvis.env", env_text)
        names = zf.namelist()
    print(f"Built {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, {len(names)} files):")
    for n in names:
        print(f"  {n}")


if __name__ == "__main__":
    main()
