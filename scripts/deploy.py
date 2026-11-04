#!/usr/bin/env python3
"""
Deploy Jarvis to AWS Lambda.
Run from the jarvis/ directory: python scripts/deploy.py
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

FUNCTION_NAME = "jarvis"
REGION = "eu-central-1"

ROOT = Path(__file__).parent.parent  # jarvis/


def run(cmd, **kwargs):
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"ERROR: command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result


def main():
    os.chdir(ROOT)

    if not (ROOT / "lambda_function.py").exists():
        print("Error: run this script from the jarvis/ directory")
        sys.exit(1)

    # 1. Clean previous build
    print("\n==> Cleaning previous build...")
    shutil.rmtree(ROOT / "package", ignore_errors=True)
    (ROOT / "lambda.zip").unlink(missing_ok=True)

    # 2. Install dependencies (Linux-compatible wheels for Lambda)
    print("\n==> Installing dependencies into package/...")
    run([
        sys.executable, "-m", "pip", "install",
        "-r", "requirements.txt",
        "-t", "package/",
        "--platform", "manylinux2014_x86_64",
        "--only-binary=:all:",
        "--python-version", "3.12",
        "--quiet"
    ])

    # 3. Copy source files
    print("\n==> Copying source files...")
    source_files = [
        "lambda_function.py",
        "intent_handlers.py",
        "agent.py",
        "config.py",
        "wiki_manager.py",
        "ssml_builder.py",
    ]
    for f in source_files:
        shutil.copy(ROOT / f, ROOT / "package" / f)

    shutil.copytree(ROOT / "tools", ROOT / "package" / "tools", dirs_exist_ok=True)

    # 4. Create zip
    print("\n==> Creating lambda.zip...")
    zip_path = ROOT / "lambda.zip"
    package_dir = ROOT / "package"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in package_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(package_dir))
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  lambda.zip created ({size_mb:.1f} MB)")

    # 5. Upload to Lambda
    print(f"\n==> Uploading to Lambda (function: {FUNCTION_NAME}, region: {REGION})...")
    run([
        "aws", "lambda", "update-function-code",
        "--function-name", FUNCTION_NAME,
        "--zip-file", f"fileb://lambda.zip",
        "--region", REGION,
        "--output", "text"
    ])

    print("\nDone! Lambda function updated.")
    print("Check the Alexa Developer Console to test with the simulator.")


if __name__ == "__main__":
    main()
