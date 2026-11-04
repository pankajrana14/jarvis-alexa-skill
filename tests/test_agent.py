import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch


def _text_block(text):
    return {"type": "text", "text": text}


def _tool_use_block(name, tool_id, inputs):
    return {"type": "tool_use", "name": name, "id": tool_id, "input": inputs}


def _response(stop_reason, *blocks):
    return {"stop_reason": stop_reason, "content": list(blocks)}


def _text_response(text):
    return _response("end_turn", _text_block(text))


def _tool_response(name, tool_id, inputs):
    return _response("tool_use", _tool_use_block(name, tool_id, inputs))


class _FakeApi:
    """Stands in for agent._post_messages; records each request body."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, body):
        self.calls.append(body)
        return self.responses.pop(0)


def _mock_client(*responses):
    return _FakeApi(*responses)


def _run(api, query="Hello", history=None):
    from agent import run_agent
    with patch("agent._post_messages", api):
        return run_agent(query, history or [], "# Wiki Index", MagicMock())


def test_run_agent_returns_text_for_simple_query():
    client = _mock_client(_text_response("Paris is the capital of France."))
    assert _run(client, "Capital of France?") == "Paris is the capital of France."


def test_run_agent_executes_search_tool_and_feeds_result_back():
    client = _mock_client(
        _tool_response("search_web", "t1", {"query": "weather Berlin"}),
        _text_response("It is 15 degrees in Berlin."),
    )
    with patch("agent.search_web", return_value="Berlin: 15C, cloudy") as mock_search:
        result = _run(client, "What is the weather in Berlin?")

    mock_search.assert_called_once_with("weather Berlin")
    assert "Berlin" in result

    second_call_messages = client.calls[1]["messages"]
    assistant_turn, tool_result_turn = second_call_messages[-2], second_call_messages[-1]
    assert assistant_turn["role"] == "assistant"
    assert tool_result_turn["role"] == "user"
    assert tool_result_turn["content"] == [
        {"type": "tool_result", "tool_use_id": "t1", "content": "Berlin: 15C, cloudy"}
    ]


def test_run_agent_returns_all_tool_results_in_one_user_message():
    both = _response(
        "tool_use",
        _tool_use_block("search_web", "a", {"query": "x"}),
        _tool_use_block("read_wiki", "b", {"topic": "y"}),
    )
    client = _mock_client(both, _text_response("done"))
    with patch("agent.search_web", return_value="S"), patch("agent.read_wiki", return_value="W"):
        _run(client)

    last = client.calls[1]["messages"][-1]
    assert [b["tool_use_id"] for b in last["content"]] == ["a", "b"]


def test_run_agent_executes_read_wiki_tool():
    client = _mock_client(
        _tool_response("read_wiki", "t2", {"topic": "user profile"}),
        _text_response("Your name is Pankaj."),
    )
    with patch("agent.read_wiki", return_value="# Profile\nName: Pankaj") as mock_read:
        result = _run(client, "What is my name?")

    mock_read.assert_called_once_with("user profile")
    assert "Pankaj" in result


def test_run_agent_includes_history_and_system_prompt():
    client = _mock_client(_text_response("Sure!"))
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    _run(client, "Tell me more.", history)

    kwargs = client.calls[-1]
    assert "Jarvis" in kwargs["system"]
    # 2 history + new user message
    assert len(kwargs["messages"]) == 3
    assert kwargs["messages"][0]["content"] == "Hello"
    assert kwargs["messages"][-1] == {"role": "user", "content": "Tell me more."}


def test_run_agent_sends_tools_in_anthropic_format():
    client = _mock_client(_text_response("Hi"))
    _run(client)

    tools = client.calls[-1]["tools"]
    assert {t["name"] for t in tools} == {"get_weather", "search_web", "read_wiki", "update_wiki"}
    assert all("input_schema" in t and "description" in t for t in tools)


def test_run_agent_returns_fallback_when_cut_off_at_max_tokens():
    client = _mock_client(_response("max_tokens", _text_block("The answer is")))
    assert _run(client) == "I encountered an issue. Please try again."


def test_run_agent_strips_litellm_style_provider_prefix(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "anthropic/claude-haiku-5-5")
    client = _mock_client(_text_response("Hi"))
    _run(client)
    assert client.calls[-1]["model"] == "claude-haiku-5-5"


def test_run_agent_disables_thinking_for_haiku_5_5(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-5-5")
    client = _mock_client(_text_response("Hi"))
    _run(client)
    assert client.calls[-1]["thinking"] == {"type": "disabled"}


def test_run_agent_uses_between_tools_thinking_for_sonnet_5_5(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")
    client = _mock_client(_text_response("Hi"))
    _run(client)
    assert client.calls[-1]["thinking"] == {"type": "between_tools"}


def test_run_agent_raises_without_llm_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        _run(_mock_client())


def test_post_messages_sends_anthropic_headers_and_body(monkeypatch):
    import agent
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"stop_reason": "end_turn", "content": []}
    with patch("agent.requests.post", return_value=resp) as mock_post:
        assert agent._post_messages({"model": "m"}) == {"stop_reason": "end_turn", "content": []}

    url = mock_post.call_args[0][0]
    kwargs = mock_post.call_args[1]
    assert url == "https://api.anthropic.com/v1/messages"
    assert kwargs["headers"]["x-api-key"] == "k-test"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"] == {"model": "m"}


def test_post_messages_retries_once_on_overload(monkeypatch):
    import agent
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    busy = MagicMock(status_code=529)
    ok = MagicMock(status_code=200)
    ok.json.return_value = {"stop_reason": "end_turn", "content": []}
    with patch("agent.requests.post", side_effect=[busy, ok]) as mock_post, patch("agent.time.sleep"):
        agent._post_messages({"model": "m"})
    assert mock_post.call_count == 2


def test_post_messages_raises_on_client_error(monkeypatch):
    import agent
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    bad = MagicMock(status_code=401, text='{"error":"invalid x-api-key"}')
    with patch("agent.requests.post", return_value=bad):
        with pytest.raises(RuntimeError, match="401"):
            agent._post_messages({"model": "m"})
