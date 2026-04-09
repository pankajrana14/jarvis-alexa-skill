import boto3
import os
from typing import Optional


def _s3():
    return boto3.client("s3")


def _bucket(bucket_name: Optional[str] = None) -> str:
    return bucket_name or os.environ["S3_BUCKET_NAME"]


def read_wiki(topic: str, bucket_name: Optional[str] = None) -> str:
    """Read a wiki page from S3 by topic name."""
    bucket = _bucket(bucket_name)
    s3 = _s3()

    # Special handling for user profile requests
    if any(w in topic.lower() for w in ("profile", "user", "me", "my")):
        try:
            response = s3.get_object(Bucket=bucket, Key="wiki/user/profile.md")
            return response["Body"].read().decode("utf-8")
        except Exception:
            pass

    key = f"wiki/topics/{topic.lower().replace(' ', '_')}.md"
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")
    except Exception:
        return f"No wiki page found for '{topic}'."


def update_wiki(topic: str, content: str, bucket_name: Optional[str] = None) -> str:
    """Write or update a wiki page in S3."""
    bucket = _bucket(bucket_name)
    s3 = _s3()

    if any(w in topic.lower() for w in ("profile", "user", "me", "my")):
        key = "wiki/user/profile.md"
    else:
        key = f"wiki/topics/{topic.lower().replace(' ', '_')}.md"

    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content.encode("utf-8"),
            ContentType="text/markdown",
        )
        return f"Updated wiki page for '{topic}'."
    except Exception as e:
        return f"Failed to update wiki for '{topic}': {e}"
