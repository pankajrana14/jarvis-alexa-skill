import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


def _text_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


def _tool_response(name: str, tool_id: str, inputs: dict):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.id = tool_id
    block.input = inputs
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = [block]
    return resp


def test_run_agent_returns_text_for_simple_query():
    from claude_agent import run_agent
    wiki_manager = MagicMock()

    with patch("claude_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response("Paris is the capital of France.")

        result = run_agent("Capital of France?", [], "# Wiki Index", wiki_manager)

    assert result == "Paris is the capital of France."


def test_run_agent_executes_search_tool_and_feeds_result_back():
    from claude_agent import run_agent
    wiki_manager = MagicMock()

    with patch("claude_agent.anthropic.Anthropic") as mock_cls:
        with patch("claude_agent.search_web", return_value="Berlin: 15°C, cloudy") as mock_search:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [
                _tool_response("search_web", "t1", {"query": "weather Berlin"}),
                _text_response("It is 15 degrees in Berlin."),
            ]

            result = run_agent("What is the weather in Berlin?", [], "# Wiki Index", wiki_manager)

    mock_search.assert_called_once_with("weather Berlin")
    assert "Berlin" in result


def test_run_agent_executes_read_wiki_tool():
    from claude_agent import run_agent
    wiki_manager = MagicMock()

    with patch("claude_agent.anthropic.Anthropic") as mock_cls:
        with patch("claude_agent.read_wiki", return_value="# Profile\nName: Pankaj") as mock_read:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [
                _tool_response("read_wiki", "t2", {"topic": "user profile"}),
                _text_response("Your name is Pankaj."),
            ]

            result = run_agent("What is my name?", [], "# Wiki Index", wiki_manager)

    mock_read.assert_called_once_with("user profile")
    assert "Pankaj" in result


def test_run_agent_returns_timeout_message_when_time_exceeded():
    from claude_agent import run_agent
    wiki_manager = MagicMock()

    time_values = [0.0, 100.0]  # second call to time.time() returns far-future value

    with patch("claude_agent.anthropic.Anthropic") as mock_cls:
        with patch("claude_agent.time.time", side_effect=time_values):
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            result = run_agent("test", [], "# Wiki Index", wiki_manager, timeout=6.5)

    assert "too long" in result.lower()


def test_run_agent_includes_history_in_messages():
    from claude_agent import run_agent
    wiki_manager = MagicMock()
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    with patch("claude_agent.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response("Sure!")

        run_agent("Tell me more.", history, "# Wiki Index", wiki_manager)

        call_kwargs = mock_client.messages.create.call_args[1]
        messages = call_kwargs["messages"]
        # history + new user message = 3 items
        assert len(messages) == 3
        assert messages[0]["content"] == "Hello"
