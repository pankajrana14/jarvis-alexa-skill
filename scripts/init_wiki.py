#!/usr/bin/env python3
"""
Initialize the S3 wiki bucket with default pages.
Run once after creating the S3 bucket:
    python scripts/init_wiki.py jarvis-wiki
"""
import boto3
import sys


def init_wiki(bucket_name: str) -> None:
    s3 = boto3.client("s3")

    pages = {
        "wiki/index.md": (
            "# Jarvis Wiki Index\n\n"
            "This wiki stores personal context for Jarvis.\n\n"
            "## Pages\n"
            "- `wiki/user/profile.md` — user profile and preferences\n"
            "- `wiki/log.md` — session log\n\n"
            "## Topics\n"
            "No topic pages yet. They will be created automatically as you use Jarvis.\n"
        ),
        "wiki/log.md": "# Session Log\n\nNo sessions yet.\n",
        "wiki/user/profile.md": (
            "# User Profile\n\n"
            "No information yet. Jarvis will fill this in as it learns about you.\n"
        ),
    }

    for key, content in pages.items():
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown",
        )
        print(f"  Created: s3://{bucket_name}/{key}")

    print(f"\nWiki initialized in s3://{bucket_name}/")
    print("Next step: set S3_BUCKET_NAME environment variable in Lambda.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/init_wiki.py <bucket-name>")
        sys.exit(1)
    init_wiki(sys.argv[1])
