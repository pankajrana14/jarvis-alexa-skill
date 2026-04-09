import anthropic
import os
import time
from typing import Any, Dict, List

from tools.search import search_web
from tools.wiki import read_wiki, update_wiki
from wiki_manager import WikiManager

TOOLS = [
    {
        "name": "search_web",
        "description": (
            "Search the internet for current, real-time, or factual information. "
            "Use for news, weather, prices, sports scores, or recent events."
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
            "Update or create a wiki page with new information. "
            "Use at the end of a session to remember new user facts or important topics discussed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic for the page"},
                "content": {
                    "type": "string",
                    "description": "Full markdown content for the page",
                },
            },
            "required": ["topic", "content"],
        },
    },
]

_SYSTEM_PROMPT = """You are Jarvis, an AI voice assistant running on an Amazon Alexa Echo Dot.

Rules:
- Respond in natural, conversational speech. No markdown, no bullet points, no headers, no lists.
- Keep responses under 500 words. Shorter is better for voice.
- Use search_web for time-sensitive queries: news, weather, prices, sports, recent events.
- Use read_wiki to recall personal context before answering personal questions.
- Use update_wiki at the end of the session to save new facts about the user or important topics.
- If you are running out of time, give a brief partial answer rather than nothing.

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


def run_agent(
    query: str,
    history: List[Dict],
    wiki_index: str,
    wiki_manager: WikiManager,
    timeout: float = 6.5,
) -> str:
    """Run the Claude agent with a tool-use loop. Returns speakable text."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system = _SYSTEM_PROMPT.format(wiki_index=wiki_index)
    messages = list(history) + [{"role": "user", "content": query}]
    start = time.time()

    for _ in range(5):  # max 5 tool-use rounds
        if time.time() - start > timeout:
            return "I'm taking too long to answer that. Please ask me again."

        remaining = timeout - (time.time() - start)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=TOOLS,
            timeout=max(remaining, 1.0),
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "I'm not sure how to answer that."

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _execute_tool(block.name, block.input, wiki_manager)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return "I encountered an issue. Please try again."
