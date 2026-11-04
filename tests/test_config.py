import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import config


def test_bucket_name_prefers_explicit_argument(monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", "env-bucket")
    assert config.bucket_name("explicit") == "explicit"


def test_bucket_name_uses_s3_bucket_name(monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", "env-bucket")
    monkeypatch.setenv("S3_PERSISTENCE_BUCKET", "hosted-bucket")
    assert config.bucket_name() == "env-bucket"


def test_bucket_name_falls_back_to_alexa_hosted_bucket(monkeypatch):
    monkeypatch.delenv("S3_BUCKET_NAME", raising=False)
    monkeypatch.setenv("S3_PERSISTENCE_BUCKET", "hosted-bucket")
    assert config.bucket_name() == "hosted-bucket"


def test_bucket_name_raises_when_unset(monkeypatch):
    monkeypatch.delenv("S3_BUCKET_NAME", raising=False)
    monkeypatch.delenv("S3_PERSISTENCE_BUCKET", raising=False)
    with pytest.raises(RuntimeError):
        config.bucket_name()


def test_load_bundled_env_reads_file_without_overriding(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_TEST_NEW=from-file\nJARVIS_TEST_EXISTING=from-file\n")
    monkeypatch.delenv("JARVIS_TEST_NEW", raising=False)
    monkeypatch.setenv("JARVIS_TEST_EXISTING", "from-env")

    config.load_bundled_env(env_file)

    assert os.environ["JARVIS_TEST_NEW"] == "from-file"
    assert os.environ["JARVIS_TEST_EXISTING"] == "from-env"
    monkeypatch.delenv("JARVIS_TEST_NEW", raising=False)


def test_load_bundled_env_ignores_missing_file(tmp_path):
    config.load_bundled_env(tmp_path / "missing.env")  # must not raise
