"""End-to-end routing through the real ASK dispatcher (lambda_function.lambda_handler)
with Alexa-shaped IntentRequests. run_agent and the wiki are patched; nothing hits the
network. Checks that each kind of utterance reaches the agent with its meaning intact,
that explicit memory requests are saved (and failures never claimed as saved), and
that plain statements are not saved."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch

import lambda_function
from utterance_frames import FRAMES


def _event(intent, slots=None, attributes=None):
    slot_json = {name: {"name": name, "value": value, "confirmationStatus": "NONE"}
                 for name, value in (slots or {}).items()}
    sysctx = {"application": {"applicationId": "amzn1.ask.skill.test"}, "user": {"userId": "u"},
              "device": {"deviceId": "d", "supportedInterfaces": {}},
              "apiEndpoint": "https://api.eu.amazonalexa.com", "apiAccessToken": "x"}
    return {
        "version": "1.0",
        "session": {"new": False, "sessionId": "amzn1.echo-api.session.test-12345678",
                    "application": {"applicationId": "amzn1.ask.skill.test"},
                    "attributes": attributes or {}, "user": {"userId": "u"}},
        "context": {"System": sysctx},
        "request": {"type": "IntentRequest", "requestId": "r", "timestamp": "2026-11-04T20:00:00Z",
                    "locale": "en-US",
                    "intent": {"name": intent, "confirmationStatus": "NONE", "slots": slot_json}},
    }


def _speech(out):
    return out["response"]["outputSpeech"]["ssml"]


def _keeps_session_open(out):
    return out["response"].get("shouldEndSession") is False and "reprompt" in out["response"]


@pytest.fixture
def agent(monkeypatch):
    import intent_handlers
    monkeypatch.setattr(intent_handlers, "_wiki_index_cache", "")  # module cache persists across tests
    with patch("intent_handlers.run_agent", return_value="Agent answer.") as run, \
         patch("intent_handlers.WikiManager") as wm_cls, \
         patch("intent_handlers.send_progressive_response"):
        wm_cls.return_value.get_index.return_value = "# Wiki Index"
        wm_cls.return_value.get_profile.return_value = ""
        yield run


@pytest.mark.parametrize("intent, slot, value, expected", [
    # wh / yes-no questions keep their question word
    ("WhatsQuestionIntent", "question", "the weather in Berlin", "what's the weather in Berlin"),
    ("HowQuestionIntent", "question", "do I reset my router", "how do I reset my router"),
    ("CanQuestionIntent", "question", "you translate good morning into Spanish",
     "can you translate good morning into Spanish"),
    ("DidQuestionIntent", "question", "it rain yesterday in Paris", "did it rain yesterday in Paris"),
    # requests keep the verb
    ("CompareRequestIntent", "request", "electric and petrol cars", "compare electric and petrol cars"),
    ("GiveMeAdviceOnRequestIntent", "request", "sleeping better", "give me advice on sleeping better"),
    # statements keep the relation that used to be lost
    ("IStatementIntent", "statement", "prefer tea over coffee", "I prefer tea over coffee"),
    ("MyStatementIntent", "statement", "name is Pankaj", "my name is Pankaj"),
    ("ImStatementIntent", "statement", "allergic to peanuts", "I'm allergic to peanuts"),
    # follow-ups and corrections
    ("AndFollowUpIntent", "followup", "in Hamburg", "and in Hamburg"),
    ("ActuallyCorrectionIntent", "correction", "I meant tomorrow",
     "Correction to what I said before: actually I meant tomorrow"),
    # generic carriers: the slot is already the whole question
    ("QueryIntent", "query", "who wrote Faust", "who wrote Faust"),
])
def test_utterances_reach_the_agent_with_meaning_intact(agent, intent, slot, value, expected):
    out = lambda_function.lambda_handler(_event(intent, {slot: value}), None)
    assert agent.call_args[0][0] == expected
    assert "Agent answer." in _speech(out)
    assert _keeps_session_open(out)


def test_bare_creative_request_uses_its_default_text(agent):
    lambda_function.lambda_handler(_event("JokeRequestIntent"), None)
    assert agent.call_args[0][0] == "Tell me a joke."


def test_question_with_empty_slot_asks_again_without_calling_agent(agent):
    out = lambda_function.lambda_handler(_event("WhatQuestionIntent", {"question": ""}), None)
    agent.assert_not_called()
    assert _keeps_session_open(out)


def test_every_frame_intent_is_handled(agent):
    for name, frame in FRAMES.items():
        out = lambda_function.lambda_handler(_event(name, {frame.slot: "something"}), None)
        assert "I ran into a problem" not in _speech(out), name


def test_statement_is_context_only_and_not_saved(agent):
    with patch("intent_handlers.update_wiki") as save:
        lambda_function.lambda_handler(_event("IStatementIntent", {"statement": "prefer tea"}), None)
    save.assert_not_called()
    agent.assert_called_once()


def test_remember_saves_immediately_and_confirms(agent):
    with patch("intent_handlers.update_wiki", return_value="Updated wiki page for 'user profile'.") as save:
        out = lambda_function.lambda_handler(_event("RememberIntent", {"fact": "my name is Pankaj"}), None)

    topic, content = save.call_args[0]
    assert topic == "user profile"
    assert "my name is Pankaj" in content
    assert "saved" in _speech(out).lower() and "my name is Pankaj" in _speech(out)
    agent.assert_not_called()
    assert _keeps_session_open(out)
    history = out["sessionAttributes"]["history"]
    assert history[-2]["content"] == "Remember that my name is Pankaj"


@pytest.mark.parametrize("failure", [
    {"return_value": "Failed to update wiki for 'user profile': AccessDenied"},
    {"side_effect": RuntimeError("No S3 bucket configured")},
])
def test_remember_failure_is_never_reported_as_saved(agent, failure):
    with patch("intent_handlers.update_wiki", **failure):
        out = lambda_function.lambda_handler(_event("RememberIntent", {"fact": "I prefer tea"}), None)

    speech = _speech(out).lower()
    assert "couldn't save" in speech
    assert "saved to your notes" not in speech
    assert _keeps_session_open(out)


def test_bare_remember_asks_what_to_remember_and_saves_nothing(agent):
    with patch("intent_handlers.update_wiki") as save:
        out = lambda_function.lambda_handler(_event("RememberIntent"), None)
    save.assert_not_called()
    assert "remember that" in _speech(out).lower()
    assert _keeps_session_open(out)


def test_fallback_offers_short_retry_and_keeps_session_open(agent):
    out = lambda_function.lambda_handler(_event("AMAZON.FallbackIntent"), None)
    agent.assert_not_called()
    assert len(_speech(out).split()) <= 30
    assert _keeps_session_open(out)


def test_saved_profile_notes_are_given_to_the_agent_every_turn(agent):
    with patch("intent_handlers.WikiManager") as wm_cls:
        wm_cls.return_value.get_index.return_value = "# Wiki Index"
        wm_cls.return_value.get_profile.return_value = "# User Profile\n- my favourite city is Lisbon"
        lambda_function.lambda_handler(_event("WhatsQuestionIntent", {"question": "my favourite city"}), None)

    context = agent.call_args[0][2]
    assert "my favourite city is Lisbon" in context


def test_statement_reply_rules_forbid_implying_it_was_saved():
    import agent as agent_module
    prompt = agent_module._SYSTEM_PROMPT
    assert "remember that" in prompt.lower()
    assert "don't say you'll remember" in prompt.lower()


# --- "yes ..." continuations: the opening word and every following word reach the agent ------

@pytest.mark.parametrize("intent, value, expected", [
    ("YesFollowUpIntent", "explain Schadenfreude with an example", "yes explain Schadenfreude with an example"),
    ("YesFollowUpIntent", "what is the capital of Peru", "yes what is the capital of Peru"),
    ("YeahFollowUpIntent", "and what about tomorrow", "yeah and what about tomorrow"),
    ("YepFollowUpIntent", "the second one please", "yep the second one please"),
    ("OkayFollowUpIntent", "tell me more about Berlin", "okay tell me more about Berlin"),
])
def test_yes_prefixed_speech_keeps_every_word(agent, intent, value, expected):
    out = lambda_function.lambda_handler(_event(intent, {"followup": value}), None)
    assert agent.call_args[0][0] == expected
    assert _keeps_session_open(out)


def test_yes_with_german_word_keeps_every_word_without_any_word_list(agent):
    lambda_function.lambda_handler(_event("YesFollowUpIntent", {"followup": "I meant Mehrwegflasche"}), None)
    assert agent.call_args[0][0] == "yes I meant Mehrwegflasche"


def test_yes_with_a_personal_statement_is_context_not_saved(agent):
    with patch("intent_handlers.update_wiki") as save:
        lambda_function.lambda_handler(_event("YesFollowUpIntent", {"followup": "I prefer tea"}), None)
    assert agent.call_args[0][0] == "yes I prefer tea"
    save.assert_not_called()


def test_standalone_yes_still_uses_the_builtin_contextual_handler(agent):
    lambda_function.lambda_handler(_event("AMAZON.YesIntent"), None)
    assert agent.call_args[0][0] == "Yes."   # plain, so it can't read as consent to an older offer


# --- general German recovery plumbing ---------------------------------------------------------

def test_spelled_word_reaches_the_agent_letter_by_letter(agent):
    lambda_function.lambda_handler(_event("ItsSpelledStatementIntent", {"statement": "m e h r w e g"}), None)
    assert agent.call_args[0][0] == "it's spelled m e h r w e g"


def test_no_goes_to_the_agent_so_it_can_follow_up_in_context(agent):
    out = lambda_function.lambda_handler(_event("AMAZON.NoIntent"), None)
    assert agent.call_args[0][0] == "No."
    assert _keeps_session_open(out)


def test_garbled_text_is_passed_through_unchanged_with_no_word_list_notes(agent):
    lambda_function.lambda_handler(_event("IsQuestionIntent", {"question": "there a malmer flasher on it if there is any font available"}), None)
    assert agent.call_args[0][0] == "is there a malmer flasher on it if there is any font available"


def test_navigate_home_ends_the_session(agent):
    out = lambda_function.lambda_handler(_event("AMAZON.NavigateHomeIntent"), None)
    assert out["response"].get("shouldEndSession") is True


def test_requests_are_logged_with_raw_slot_text(agent, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        lambda_function.lambda_handler(_event("WhatQuestionIntent", {"question": "is a mare vague flasher"}), None)
    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("request "))
    assert "WhatQuestionIntent" in line and "mare vague flasher" in line
