import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from moto import mock_aws


@mock_aws
def test_get_index_returns_default_when_file_missing():
    from wiki_manager import WikiManager
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    wm = WikiManager("test-bucket")
    result = wm.get_index()
    assert "Wiki Index" in result


@mock_aws
def test_get_index_returns_stored_content():
    from wiki_manager import WikiManager
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(Bucket="test-bucket", Key="wiki/index.md", Body=b"# My Index\n- python.md\n")

    wm = WikiManager("test-bucket")
    result = wm.get_index()
    assert "My Index" in result
    assert "python.md" in result


@mock_aws
def test_append_log_creates_entry_with_query():
    from wiki_manager import WikiManager
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    wm = WikiManager("test-bucket")
    wm.append_log("session-abc123", "What is Python?", "Python is a programming language.")

    obj = s3.get_object(Bucket="test-bucket", Key="wiki/log.md")
    content = obj["Body"].read().decode("utf-8")
    assert "What is Python?" in content


@mock_aws
def test_append_log_appends_to_existing_log():
    from wiki_manager import WikiManager
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(Bucket="test-bucket", Key="wiki/log.md", Body=b"# Session Log\n\n## Old entry\n")

    wm = WikiManager("test-bucket")
    wm.append_log("session-xyz", "New question?", "New answer.")

    obj = s3.get_object(Bucket="test-bucket", Key="wiki/log.md")
    content = obj["Body"].read().decode("utf-8")
    assert "Old entry" in content
    assert "New question?" in content


@mock_aws
def test_append_log_does_not_raise_on_s3_failure():
    from wiki_manager import WikiManager
    # Bucket does not exist — should fail silently
    wm = WikiManager("nonexistent-bucket")
    wm.append_log("s1", "q", "a")  # must not raise
