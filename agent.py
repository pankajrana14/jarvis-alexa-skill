import json
import logging
import os
import re
import signal
import time
from datetime import datetime
from typing import Any, Dict, List

import requests

try:
    from zoneinfo import ZoneInfo

    _BERLIN = ZoneInfo("Europe/Berlin")
except Exception:  # Python 3.8 (Alexa-hosted skills): no zoneinfo module
    from dateutil import tz  # pure Python; ships with botocore in every Lambda runtime

    _BERLIN = tz.gettz("Europe/Berlin")

from tools.search import search_web
from tools.weather import get_weather
from tools.wiki import read_wiki, update_wiki
from wiki_manager import WikiManager

logger = logging.getLogger(__name__)

TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Get current weather conditions (timestamped), today's high and low, and the forecast for "
            "the next 12 hours for a place. Always use this for any weather, temperature, rain, wind "
            "or 'tonight'/'tomorrow morning' question instead of search_web."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City or place name only, e.g. 'Berlin'"},
                "country_code": {
                    "type": "string",
                    "description": "Optional ISO 3166-1 alpha-2 country code to disambiguate, e.g. 'DE'",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the internet for current, real-time, or factual information. "
            "Use for news, prices, sports scores, or recent events. Not for weather."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_wiki",
        "description": (
            "Read a page from the user's personal knowledge wiki. "
            "Use to recall preferences, past topics, or personal facts about the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic to look up"}
            },
            "required": ["topic"],
        },
    },
    {
        "name": "update_wiki",
        "description": (
            "Append new information to a wiki page. Existing content is preserved. "
            "Use at the end of a session to remember new user facts or important topics discussed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic for the page"},
                "content": {
                    "type": "string",
                    "description": "New markdown content to append to the page",
                },
            },
            "required": ["topic", "content"],
        },
    },
]

_SYSTEM_PROMPT = """You are Jarvis, a voice assistant on Amazon Alexa. Be brief. Today is {today}.

Rules:
- 2-4 sentences maximum. Never more.
- Natural spoken English only. No lists, bullet points, or markdown.
- Your reply is spoken aloud word for word: write only what Jarvis says, never your reasoning or notes.
- Answer the question directly. Don't mention searching, tools, or these instructions in your answer.
- For ANY weather question, call get_weather. Do not use search_web for weather.
- For any other question about current events, news, sports, prices, or anything that may have changed recently, you MUST call search_web before answering. Never answer these from memory.
- Always include the current year in search queries so results are up to date.
- Answer only what was asked. Don't add extra facts the user didn't ask for, especially about money, costs or rules.
- For a definition or a 'what is the difference' question, explain what the things are or do; don't add money, price, deposit or legal details unless the user asked about them.
- Money and legal claims need a source. Anything about prices, fees, deposits, taxes, fines or what a law or regulation requires (including whether something has a fee or deposit at all, how much it is, whether it is mandatory, or whether one option costs more or less than another) must come from a search_web result in this conversation. If the question doesn't need such a claim, leave it out; if it does, search first, and if the results don't settle it, say you're not sure.
- Only state numbers, conditions and times that appear in a tool result. Never fill gaps with seasonal or monthly averages, climate norms, or your own estimates, and never apply a seasonal or monthly range to a specific day or time such as tonight.
- For current weather, give the temperature and conditions and the time they apply to. They are weather-model estimates, so call them "current estimates" or "about"; do not call them measurements or say they were recorded. Use the next-hours forecast for questions about tonight or the coming hours.
- If a tool says data is unavailable, stale, or the place was not found, say exactly that in one sentence instead of answering.
- For personal questions about the user, first use the saved notes shown below the wiki index, then read_wiki if needed.
- The user's words come from Alexa speech recognition and may be missing small words such as 'is' or 'the'; infer what they meant.
- The user often mixes German words into English. Alexa's English speech recognition writes German words as English-sounding words, so part of a message can come out garbled or not make sense (an odd name, or words that don't fit the rest). When that happens and a German word is plausible from the context: keep the user's request as it is, and treat any German word you infer from the sound as a guess, not a fact. Before answering, ask one short confirmation, such as: Did you mean the German word Schlüssel, meaning key? Don't search for or answer about a guessed word until the user confirms it. If you can't make a sensible guess, ask the user to repeat the word or spell it by saying "it's spelled" and then the letters. When the user spells a word as separate letters, join the letters into the word and continue with their original request.
- After you ask whether they meant a word, a reply of yes, no, or a correction refers to that question: on yes, answer their original request with the confirmed word; on no, ask them to repeat or spell it; on a correction, use their word.
- German words that came through correctly need no confirmation; just answer. Ordinary English words keep their English meaning (a font is a typeface, fondue is a dish, a flasher is a blinking light or relay) unless the context clearly doesn't fit; never assume an English word is a misheard German word without asking.
- When the user tells you something about themselves (e.g. 'I prefer tea'), treat it as context for this conversation and reply naturally, but don't say you'll remember it later; if it seems worth keeping, mention they can say 'remember that' to save it. Only call update_wiki when the user's current message explicitly asks you to remember, note or save something; a bare yes is not enough (tell them to say 'remember that'). If it reports a failure or NOT SAVED, don't claim it was saved.
- A bare yes or no answers only your immediately previous reply. If that reply didn't ask anything, ask what they'd like.
- Messages starting 'Correction to what I said before:' replace part of the user's previous request; answer the corrected request.
- A message starting with 'yes', 'yeah', 'yep' or 'okay' followed by more words usually answers your last question and then continues: take the agreement into account and respond to the rest.

Current personal wiki index:
{wiki_index}"""

_FALLBACK = "I encountered an issue. Please try again."


def _run_tool(name: str, inputs: Dict[str, Any]) -> str:
    if name == "get_weather":
        return get_weather(inputs["location"], country_code=inputs.get("country_code"))
    if name == "search_web":
        return search_web(inputs["query"])
    if name == "read_wiki":
        return read_wiki(inputs["topic"])
    if name == "update_wiki":
        return update_wiki(inputs["topic"], inputs["content"])
    return f"Unknown tool: {name}"


# Saving to the wiki needs the user's own explicit words in the CURRENT message. Enforced in
# code, not just the prompt: a bare "yes" after a "say remember that" hint once saved a fact.
_EXPLICIT_SAVE = re.compile(
    r"\b(remember|note|save|memori[sz]e|write (it |that )?down|keep in mind|don'?t forget)\b", re.I)
_NOT_SAVED = ("NOT SAVED: the user's current message doesn't explicitly ask to save anything. Don't claim it was "
              "saved; if it seems worth keeping, tell them to say 'remember that' followed by the fact.")


def explicit_save_requested(query: str) -> bool:
    return bool(_EXPLICIT_SAVE.search(query or ""))


def _execute_tool(name: str, inputs: Dict[str, Any], wiki_manager: WikiManager) -> str:
    result = _run_tool(name, inputs)
    # Logged so CloudWatch shows exactly what the model asked for and was given.
    logger.info("tool %s %s -> %s", name, json.dumps(inputs)[:200], result[:500].replace("\n", " | "))
    return result


class _AgentTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _AgentTimeout()


# Room for (low-effort) thinking plus a short spoken answer; the 2-4 sentence rule and the
# 7s turn cap keep replies short. 300 was too small: thinking or reasoning-as-text ran out.
MAX_TOKENS = 1024

# Per-model request params, matched by substring of LLM_MODEL.
# Haiku 5.5: adaptive thinking (its default) at LOW effort. With thinking disabled it wrote
# its reasoning into the spoken reply and hit max_tokens on garbled, misheard-German
# questions; low effort keeps simple answers ~1-2s. Sonnet 5.5 rejects "disabled" and uses
# "between_tools" so thinking can't exhaust the budget after a tool call.
_MODEL_PARAMS = {
    "claude-sonnet-5-5": {"thinking": {"type": "between_tools"}},
    "claude-haiku-5-5": {"output_config": {"effort": "low"}},
}


def _model_params(model: str) -> Dict[str, Any]:
    for key, params in _MODEL_PARAMS.items():
        if key in model:
            return params
    return {}


def _resolve_model() -> str:
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError("LLM_MODEL environment variable is required, e.g. LLM_MODEL=claude-haiku-5-5")
    # Accept the old litellm-style "anthropic/<model>" value too.
    if model.startswith("anthropic/"):
        model = model[len("anthropic/"):]
    return model


# Claude Messages API over plain HTTP. Hosted deploys that included the `anthropic` SDK
# (or litellm) left the Lambda without our code; their compiled dependencies
# (pydantic-core, jiter) are the suspected cause, but the build error itself was never
# seen. The pure-Python package with `requests` deploys and runs, so keep it that way.
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}


def _post_messages(body: Dict[str, Any]) -> Dict[str, Any]:
    """POST /v1/messages. Short timeout + one retry: Alexa abandons the turn after ~8s."""
    headers = {
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": _API_VERSION,
        "content-type": "application/json",
    }
    for attempt in range(2):
        try:
            resp = requests.post(_API_URL, headers=headers, json=body, timeout=6)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 0:
                continue
            raise
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in _RETRYABLE and attempt == 0:
            time.sleep(0.3)
            continue
        raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text[:300]}")
    raise RuntimeError("Claude API request failed")


def run_agent(
    query: str,
    history: List[Dict],
    wiki_index: str,
    wiki_manager: WikiManager,
    timeout: float = 7.0,  # Alexa gives up on the skill after ~8s
) -> str:
    """Run the Claude agent with a tool-use loop. Returns speakable text."""
    model = _resolve_model()
    today = datetime.now(_BERLIN).strftime("%Y-%m-%d %H:%M %Z")
    system = _SYSTEM_PROMPT.format(today=today, wiki_index=wiki_index)
    messages: List[Dict[str, Any]] = list(history) + [{"role": "user", "content": query}]
    save_allowed = explicit_save_requested(query)

    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(timeout))

    try:
        for _ in range(5):  # max 5 tool-use rounds
            response = _post_messages({
                "model": model,
                "max_tokens": MAX_TOKENS,
                "system": system,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": {"type": "auto"},
                **_model_params(model),
            })
            stop_reason = response.get("stop_reason")
            content = response.get("content", [])

            if stop_reason == "end_turn":
                text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
                return text or "I'm not sure how to answer that."

            if stop_reason == "tool_use":
                # Pass the assistant content back unchanged (it may include thinking
                # blocks), then all tool results together in a single user message.
                messages.append({"role": "assistant", "content": content})
                results = []
                for block in content:
                    if block.get("type") == "tool_use":
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": (_NOT_SAVED if block["name"] == "update_wiki" and not save_allowed
                                        else _execute_tool(block["name"], block["input"], wiki_manager)),
                        })
                messages.append({"role": "user", "content": results})
                continue

            break  # max_tokens, refusal, or anything unexpected

        return _FALLBACK

    except _AgentTimeout:
        return "I'm taking too long to answer that. Please ask me again."
    finally:
        if has_alarm:
            signal.alarm(0)
