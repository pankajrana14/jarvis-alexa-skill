import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ssml_builder import text_to_ssml, clean_for_speech


def test_text_to_ssml_wraps_in_speak_tags():
    assert text_to_ssml("Hello world") == "<speak>Hello world</speak>"


def test_text_to_ssml_escapes_ampersand():
    result = text_to_ssml("Fish & chips")
    assert "&amp;" in result
    assert "& " not in result  # raw ampersand gone


def test_text_to_ssml_escapes_angle_brackets():
    result = text_to_ssml("a < b > c")
    assert "&lt;" in result
    assert "&gt;" in result


def test_clean_for_speech_removes_markdown_headers():
    result = clean_for_speech("## Hello\nworld")
    assert "##" not in result
    assert "Hello" in result


def test_clean_for_speech_removes_bold():
    result = clean_for_speech("This is **bold** text")
    assert "**" not in result
    assert "bold" in result


def test_clean_for_speech_removes_bullet_points():
    result = clean_for_speech("Items:\n- one\n- two")
    assert "- " not in result
    assert "one" in result


def test_clean_for_speech_removes_code_blocks():
    result = clean_for_speech("Use `print()` to output")
    assert "`" not in result
    assert "print" in result


def test_clean_for_speech_truncates_at_500_words():
    long_text = "word " * 600
    result = clean_for_speech(long_text)
    assert len(result.split()) <= 501
