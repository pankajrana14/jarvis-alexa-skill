import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
from unittest.mock import MagicMock, patch


def _make_message(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    return msg


def _text_response(text: str):
    msg = _make_message(content=text)
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _tool_response(name: str, tool_id: str, inputs: dict):
    tool_call = MagicMock()
    tool_call.id = tool_id
    tool_call.function.name = name
    tool_call.function.arguments = json.dumps(inputs)
    msg = _make_message(tool_calls=[tool_call])
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_run_agent_returns_text_for_simple_query():
    from agent import run_agent
    wiki_manager = MagicMock()

    with patch("agent.litellm.completion", return_value=_text_response("Paris is the capital of France.")):
        result = run_agent("Capital of France?", [], "# Wiki Index", wiki_manager)

    assert result == "Paris is the capital of France."


def test_run_agent_executes_search_tool_and_feeds_result_back():
    from agent import run_agent
    wiki_manager = MagicMock()

    with patch("agent.litellm.completion") as mock_completion:
        with patch("agent.search_web", return_value="Berlin: 15°C, cloudy") as mock_search:
            mock_completion.side_effect = [
                _tool_response("search_web", "t1", {"query": "weather Berlin"}),
                _text_response("It is 15 degrees in Berlin."),
            ]

            result = run_agent("What is the weather in Berlin?", [], "# Wiki Index", wiki_manager)

    mock_search.assert_called_once_with("weather Berlin")
    assert "Berlin" in result


def test_run_agent_executes_read_wiki_tool():
    from agent import run_agent
    wiki_manager = MagicMock()

    with patch("agent.litellm.completion") as mock_completion:
        with patch("agent.read_wiki", return_value="# Profile\nName: Pankaj") as mock_read:
            mock_completion.side_effect = [
                _tool_response("read_wiki", "t2", {"topic": "user profile"}),
                _text_response("Your name is Pankaj."),
            ]

            result = run_agent("What is my name?", [], "# Wiki Index", wiki_manager)

    mock_read.assert_called_once_with("user profile")
    assert "Pankaj" in result


def test_run_agent_includes_history_in_messages():
    from agent import run_agent
    wiki_manager = MagicMock()
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    with patch("agent.litellm.completion", return_value=_text_response("Sure!")) as mock_completion:
        run_agent("Tell me more.", history, "# Wiki Index", wiki_manager)

        call_kwargs = mock_completion.call_args[1]
        messages = call_kwargs["messages"]
        # system + 2 history + new user message = 4
        assert len(messages) == 4
        assert messages[1]["content"] == "Hello"
        assert messages[0]["role"] == "system"


def test_run_agent_raises_without_llm_model(monkeypatch):
    from agent import run_agent
    monkeypatch.delenv("LLM_MODEL", raising=False)
    wiki_manager = MagicMock()

    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        run_agent("Hello", [], "# Wiki Index", wiki_manager)
