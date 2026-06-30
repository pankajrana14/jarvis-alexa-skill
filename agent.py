import json
import os
import signal
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

import litellm

from tools.search import search_web
from tools.wiki import read_wiki, update_wiki
from wiki_manager import WikiManager

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the internet for current, real-time, or factual information. "
                "Use for news, weather, prices, sports scores, or recent events."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_wiki",
            "description": (
                "Read a page from the user's personal knowledge wiki. "
                "Use to recall preferences, past topics, or personal facts about the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to look up"}
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_wiki",
            "description": (
                "Append new information to a wiki page. Existing content is preserved. "
                "Use at the end of a session to remember new user facts or important topics discussed."
            ),
            "parameters": {
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
    },
]

_SYSTEM_PROMPT = """You are Jarvis, a voice assistant on Amazon Alexa. Be brief. Today is {today}.

Rules:
- 2-4 sentences maximum. Never more.
- Natural spoken English only. No lists, bullet points, or markdown.
- For ANY question about current events, news, weather, sports, prices, or anything that may have changed recently, you MUST call search_web before answering. Never answer these from memory.
- Always include the current year in search queries so results are up to date.
- Use read_wiki for personal questions about the user.
- Use update_wiki to remember new user facts at session end.

Current personal wiki index:
{wiki_index}"""


def _execute_tool(name: str, inputs: Dict[str, Any], wiki_manager: WikiManager) -> str:
    if name == "search_web":
        return search_web(inputs["query"])
    if name == "read_wiki":
        return read_wiki(inputs["topic"])
    if name == "update_wiki":
        return update_wiki(inputs["topic"], inputs["content"])
    return f"Unknown tool: {name}"


class _AgentTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _AgentTimeout()


def _resolve_model() -> str:
    model = os.environ.get("LLM_MODEL")
    if not model:
        raise RuntimeError(
            "LLM_MODEL environment variable is required, e.g. LLM_MODEL=groq/openai/gpt-oss-20b"
        )
    return model


def run_agent(
    query: str,
    history: List[Dict],
    wiki_index: str,
    wiki_manager: WikiManager,
    timeout: float = 12.0,
) -> str:
    """Run the configured LLM agent with a tool-use loop. Returns speakable text."""
    model = _resolve_model()
    today = datetime.now(ZoneInfo("Europe/Berlin")).strftime("%Y-%m-%d %H:%M %Z")
    system = _SYSTEM_PROMPT.format(today=today, wiki_index=wiki_index)
    messages = [{"role": "system", "content": system}] + list(history) + [{"role": "user", "content": query}]

    has_alarm = hasattr(signal, "SIGALRM")
    if has_alarm:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(timeout))

    try:
        for i in range(5):  # max 5 tool-use rounds
            response = litellm.completion(
                model=model,
                max_tokens=300,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "stop":
                return msg.content or "I'm not sure how to answer that."

            if finish_reason == "tool_calls":
                messages.append(msg)
                for tool_call in msg.tool_calls:
                    inputs = json.loads(tool_call.function.arguments)
                    result = _execute_tool(tool_call.function.name, inputs, wiki_manager)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
            else:
                break

        return "I encountered an issue. Please try again."

    except _AgentTimeout:
        return "I'm taking too long to answer that. Please ask me again."
    finally:
        if has_alarm:
            signal.alarm(0)
