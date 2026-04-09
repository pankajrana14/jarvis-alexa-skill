import boto3
import os
from datetime import datetime, timezone
from typing import Optional


class WikiManager:
    """Manages the Karpathy-style LLM wiki stored in S3."""

    def __init__(self, bucket_name: Optional[str] = None):
        self.bucket = bucket_name or os.environ["S3_BUCKET_NAME"]
        self.s3 = boto3.client("s3")

    def get_index(self) -> str:
        """Return wiki/index.md, or a default stub if it does not exist."""
        import logging
        logger = logging.getLogger(__name__)
        try:
            response = self.s3.get_object(Bucket=self.bucket, Key="wiki/index.md")
            return response["Body"].read().decode("utf-8")
        except Exception as e:
            logger.warning("Could not load wiki index: %s", e)
            return "# Wiki Index\n\nNo pages yet.\n"

    def append_log(self, session_id: str, query: str, response: str) -> None:
        """Append a Q&A entry to wiki/log.md. Failures are silently swallowed."""
        try:
            try:
                existing = self.s3.get_object(Bucket=self.bucket, Key="wiki/log.md")
                log = existing["Body"].read().decode("utf-8")
            except Exception:
                log = "# Session Log\n\n"

            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            short_id = session_id[-8:]
            entry = (
                f"\n## {timestamp} (session: {short_id})\n"
                f"**Q:** {query}\n"
                f"**A:** {response[:200]}{'...' if len(response) > 200 else ''}\n"
            )
            self.s3.put_object(
                Bucket=self.bucket,
                Key="wiki/log.md",
                Body=(log + entry).encode("utf-8"),
                ContentType="text/markdown",
            )
        except Exception:
            pass  # log failures are non-critical
