import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch


def _make_handler_input(request_type=None, intent_name=None, slot_value=None, session_id="session-123"):
    """Build a minimal mock HandlerInput."""
    hi = MagicMock()
    hi.request_envelope.session.session_id = session_id
    hi.attributes_manager.session_attributes = {}

    req = hi.request_envelope.request
    req.__class__.__name__ = request_type or "Request"

    if intent_name:
        req.intent.name = intent_name
        if slot_value:
            slot = MagicMock()
            slot.value = slot_value
            req.intent.slots = {"query": slot}
        else:
            req.intent.slots = {}

    # Make can_handle checks work with is_request_type / is_intent_name
    hi.request_envelope.request.object_type = request_type
    if intent_name:
        hi.request_envelope.request.intent.name = intent_name

    hi.response_builder.speak.return_value = hi.response_builder
    hi.response_builder.ask.return_value = hi.response_builder
    hi.response_builder.response = MagicMock()
    return hi


def test_launch_handler_speaks_welcome():
    from intent_handlers import LaunchRequestHandler
    handler = LaunchRequestHandler()
    hi = _make_handler_input(request_type="LaunchRequest")

    # Simulate can_handle via patching is_request_type
    with patch("intent_handlers.is_request_type", return_value=lambda _: True):
        handler.handle(hi)

    hi.response_builder.speak.assert_called_once()
    speech_arg = hi.response_builder.speak.call_args[0][0]
    assert "Jarvis" in speech_arg


def test_stop_handler_speaks_goodbye():
    from intent_handlers import StopIntentHandler
    handler = StopIntentHandler()
    hi = _make_handler_input(intent_name="AMAZON.StopIntent")

    with patch("intent_handlers.is_intent_name", return_value=lambda _: True):
        handler.handle(hi)

    hi.response_builder.speak.assert_called_once()
    speech_arg = hi.response_builder.speak.call_args[0][0]
    assert "Goodbye" in speech_arg or "goodbye" in speech_arg.lower()


def test_help_handler_speaks_help_text():
    from intent_handlers import HelpIntentHandler
    handler = HelpIntentHandler()
    hi = _make_handler_input(intent_name="AMAZON.HelpIntent")

    with patch("intent_handlers.is_intent_name", return_value=lambda _: True):
        handler.handle(hi)

    hi.response_builder.speak.assert_called_once()


def test_query_handler_calls_run_agent_with_query():
    from intent_handlers import UtteranceIntentHandler
    handler = UtteranceIntentHandler()
    hi = _make_handler_input(intent_name="QueryIntent", slot_value="What is Python?")

    with patch("intent_handlers.is_intent_name", return_value=lambda _: True):
        with patch("intent_handlers.run_agent", return_value="Python is a programming language.") as mock_agent:
            with patch("intent_handlers.WikiManager"):
                with patch("intent_handlers.send_progressive_response"):
                    handler.handle(hi)

    mock_agent.assert_called_once()
    call_args = mock_agent.call_args[0]
    assert call_args[0] == "What is Python?"


def test_query_handler_returns_fallback_when_slot_empty():
    from intent_handlers import UtteranceIntentHandler
    handler = UtteranceIntentHandler()
    hi = _make_handler_input(intent_name="QueryIntent", slot_value=None)
    hi.request_envelope.request.intent.slots = {}

    with patch("intent_handlers.is_intent_name", return_value=lambda _: True):
        handler.handle(hi)

    speech = hi.response_builder.speak.call_args[0][0]
    assert "didn't catch" in speech.lower() or "sorry" in speech.lower()


def test_query_handler_appends_to_session_history():
    from intent_handlers import UtteranceIntentHandler
    handler = UtteranceIntentHandler()
    hi = _make_handler_input(intent_name="QueryIntent", slot_value="Hello")

    with patch("intent_handlers.is_intent_name", return_value=lambda _: True):
        with patch("intent_handlers.run_agent", return_value="Hi there!"):
            with patch("intent_handlers.WikiManager"):
                with patch("intent_handlers.send_progressive_response"):
                    handler.handle(hi)

    history = hi.attributes_manager.session_attributes.get("history", [])
    assert any(m["content"] == "Hello" for m in history)


def test_catch_all_exception_handler_speaks_error_and_logs():
    from intent_handlers import CatchAllExceptionHandler
    handler = CatchAllExceptionHandler()
    hi = _make_handler_input()
    err = RuntimeError("boom")

    assert handler.can_handle(hi, err) is True
    with patch("intent_handlers.logger") as mock_logger:
        handler.handle(hi, err)

    mock_logger.exception.assert_called_once()
    speech_arg = hi.response_builder.speak.call_args[0][0]
    assert "problem" in speech_arg
