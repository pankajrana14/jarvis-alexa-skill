"""
SSML utilities for Alexa voice responses.

Call order: clean_for_speech(text) FIRST, then text_to_ssml(result).
text_to_ssml escapes < and > which would corrupt output if clean_for_speech ran after.
"""
import re


def text_to_ssml(text: str) -> str:
    """Wrap plain text in SSML speak tags, escaping XML special characters.

    Always call clean_for_speech() before this function.
    """
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<speak>{text}</speak>"


def clean_for_speech(text: str) -> str:
    """Strip markdown formatting so text sounds natural when spoken by Alexa."""
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic (*** ** * ___ __ _)
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove markdown links, keep display text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Remove bullet points
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    # Remove numbered list markers
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    # Truncate to 500 words
    words = text.split()
    if len(words) > 500:
        text = " ".join(words[:500]) + "."
    return text
