import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
import pytest
from moto import mock_aws


@mock_aws
def test_read_wiki_returns_page_content():
    from tools.wiki import read_wiki
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(Bucket="test-bucket", Key="wiki/topics/python.md", Body=b"# Python\nA programming language.")

    result = read_wiki("python")
    assert "Python" in result
    assert "programming language" in result


@mock_aws
def test_read_wiki_returns_not_found_message_for_missing_topic():
    from tools.wiki import read_wiki
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    result = read_wiki("nonexistent_topic_xyz")
    assert "No wiki page found" in result


@mock_aws
def test_update_wiki_creates_page_in_s3():
    from tools.wiki import update_wiki
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    result = update_wiki("Berlin", "# Berlin\nCapital of Germany.")
    assert "Updated wiki page" in result

    obj = s3.get_object(Bucket="test-bucket", Key="wiki/topics/berlin.md")
    assert "Capital of Germany" in obj["Body"].read().decode("utf-8")


@mock_aws
def test_update_wiki_user_profile_stores_at_profile_key():
    from tools.wiki import update_wiki
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")

    update_wiki("user profile", "# User Profile\nName: Pankaj")

    obj = s3.get_object(Bucket="test-bucket", Key="wiki/user/profile.md")
    assert "Pankaj" in obj["Body"].read().decode("utf-8")


@mock_aws
def test_read_wiki_normalizes_topic_to_lowercase_snake_case():
    from tools.wiki import read_wiki
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="test-bucket")
    s3.put_object(Bucket="test-bucket", Key="wiki/topics/machine_learning.md", Body=b"# ML page")

    result = read_wiki("Machine Learning")
    assert "ML page" in result
