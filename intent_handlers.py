import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.services.directive import SendDirectiveRequest, Header, SpeakDirective

from datetime import datetime, timezone

from ask_sdk_core.dispatch_components import AbstractRequestInterceptor

from agent import run_agent
from tools.wiki import update_wiki
from utterance_frames import FRAMES, reconstruct
from wiki_manager import WikiManager
from ssml_builder import text_to_ssml, clean_for_speech

logger = logging.getLogger(__name__)

# Module-level wiki index cache — persists across warm Lambda invocations
_wiki_index_cache: str = ""

_WELCOME = "Hi, I'm Jarvis. What would you like to know?"
_HELP = "You can ask me anything. Just say your question. Say stop to exit."
_STOP = "Goodbye!"
_FALLBACK = "Sorry, I didn't catch that. Try starting with what, how, or tell me, or say remember that."
_RETRY = "Sorry, I missed the rest of that. Please say it again."
_REMEMBER_WHAT = "What should I remember? Say remember that, followed by the fact."
_ERROR = "I ran into a problem. Please try again."


def send_progressive_response(handler_input: HandlerInput, text: str) -> None:
    """Fire-and-forget progressive response to reduce perceived latency."""
    try:
        request_id = handler_input.request_envelope.request.request_id
        client = handler_input.service_client_factory.get_directive_service()
        client.enqueue(
            SendDirectiveRequest(
                header=Header(request_id=request_id),
                directive=SpeakDirective(speech=text_to_ssml(text)),
            )
        )
    except Exception as e:
        logger.warning("Progressive response failed: %s", e)


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak(text_to_ssml(_WELCOME))
            .ask(text_to_ssml("What would you like to know?"))
            .response
        )


def _handle_query(handler_input: HandlerInput, query: str) -> Response:
    """Shared logic for all query-type intents."""
    send_progressive_response(handler_input, "Let me think about that.")

    session_attrs = handler_input.attributes_manager.session_attributes
    history = session_attrs.get("history", [])

    wiki_manager = WikiManager()
    global _wiki_index_cache
    if not _wiki_index_cache:
        _wiki_index_cache = wiki_manager.get_index()
    wiki_context = _wiki_index_cache
    # Saved notes are read every turn (not cached) so a fact saved a moment ago is used.
    profile = wiki_manager.get_profile()
    if isinstance(profile, str) and profile.strip():
        wiki_context += f"\n\nSaved notes about the user (from explicit 'remember' requests):\n{profile.strip()}"

    agent_error = False
    try:
        response_text = run_agent(query, history, wiki_context, wiki_manager)
    except Exception as e:
        logger.error("Agent error: %s", e)
        response_text = _ERROR
        agent_error = True

    clean_response = clean_for_speech(response_text)

    if not agent_error:
        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": response_text})
        session_attrs["history"] = history[-10:]
        handler_input.attributes_manager.session_attributes = session_attrs

        session_id = handler_input.request_envelope.session.session_id
        wiki_manager.append_log(session_id, query, response_text)

    return (
        handler_input.response_builder
        .speak(text_to_ssml(clean_response))
        .ask(text_to_ssml("Is there anything else?"))
        .response
    )


def _slot_value(handler_input: HandlerInput, name: str):
    slots = handler_input.request_envelope.request.intent.slots or {}
    slot = slots.get(name)
    return slot.value if slot and slot.value else None


def _ask(handler_input: HandlerInput, text: str, reprompt: str = "What would you like to know?") -> Response:
    return handler_input.response_builder.speak(text_to_ssml(text)).ask(text_to_ssml(reprompt)).response


class UtteranceIntentHandler(AbstractRequestHandler):
    """All open-ended frames (questions, requests, statements, follow-ups, corrections,
    generic carriers): rebuild the user's words from lead + slot and ask the agent.
    Statements are passed as conversation context only; nothing is saved here."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        request = handler_input.request_envelope.request
        name = getattr(getattr(request, "intent", None), "name", None)
        return is_request_type("IntentRequest")(handler_input) and name in FRAMES and name != "RememberIntent"

    def handle(self, handler_input: HandlerInput) -> Response:
        frame = FRAMES[handler_input.request_envelope.request.intent.name]
        text = reconstruct(frame.intent, _slot_value(handler_input, frame.slot))
        if not text:
            return _ask(handler_input, _RETRY)
        return _handle_query(handler_input, text)


class RequestLoggingInterceptor(AbstractRequestInterceptor):
    """Log every request's intent and raw slot text to CloudWatch. Intent History needs 10+
    unique users a day, so this is how we see what Alexa's speech recognition actually
    produced, e.g. for German words spoken inside English sentences."""

    def process(self, handler_input: HandlerInput) -> None:
        try:
            request = handler_input.request_envelope.request
            intent = getattr(request, "intent", None)
            if intent is None:
                logger.info("request %s", type(request).__name__)
                return
            parts = [f"{name}={slot.value!r}" for name, slot in (intent.slots or {}).items()
                     if slot is not None and slot.value is not None]
            logger.info("request %s %s", intent.name, " ".join(parts))
        except Exception as e:  # logging must never break a request
            logger.warning("request logging failed: %s", e)


class RememberIntentHandler(AbstractRequestHandler):
    """Explicit 'remember that ...' requests: save to the user's wiki profile right away,
    and only say it was saved if the save actually succeeded."""

    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("RememberIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        fact = (_slot_value(handler_input, "fact") or "").strip()
        if not fact:
            return _ask(handler_input, _REMEMBER_WHAT, _REMEMBER_WHAT)

        saved_on = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            result = update_wiki("user profile", f"- {fact} (saved {saved_on})")
            ok = isinstance(result, str) and result.startswith("Updated wiki page")
            if not ok:
                logger.error("Remember failed: %s", result)
        except Exception as e:
            logger.exception("Remember failed: %s", e)
            ok = False

        if ok:
            speech = f"Okay, saved to your notes: {fact}."
        else:
            speech = "Sorry, I couldn't save that right now, so I won't remember it. Please try again later."

        attrs = handler_input.attributes_manager.session_attributes
        history = attrs.get("history", [])
        history.append({"role": "user", "content": f"Remember that {fact}"})
        history.append({"role": "assistant", "content": speech})
        attrs["history"] = history[-10:]
        handler_input.attributes_manager.session_attributes = attrs

        return _ask(handler_input, clean_for_speech(speech), "Is there anything else?")


class PriceQueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("PriceQueryIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return _handle_query(handler_input, "How much does it cost?")


class MoreDetailsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("MoreDetailsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return _handle_query(handler_input, "Tell me more about it.")


class GreetingIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("GreetingIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return _handle_query(handler_input, "The user greeted you. Greet them back warmly and ask what they'd like to know.")


class ThankYouIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ThankYouIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak(text_to_ssml("You're welcome! Is there anything else I can help you with?"))
            .ask(text_to_ssml("Is there anything else?"))
            .response
        )


class YesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Plain "Yes." so it answers only the last question, never an older offer.
        return _handle_query(handler_input, "Yes.")


class NoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Goes to the agent so a "no" can answer its last question in context,
        # e.g. "Did you mean Schlüssel?" -> "No" -> "Could you spell it?".
        return _handle_query(handler_input, "No.")


class StopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (
            is_intent_name("AMAZON.StopIntent")(handler_input)
            or is_intent_name("AMAZON.CancelIntent")(handler_input)
            or is_intent_name("AMAZON.NavigateHomeIntent")(handler_input)
        )

    def handle(self, handler_input: HandlerInput) -> Response:
        return handler_input.response_builder.speak(text_to_ssml(_STOP)).set_should_end_session(True).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak(text_to_ssml(_HELP))
            .ask(text_to_ssml("What would you like to know?"))
            .response
        )


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak(text_to_ssml(_FALLBACK))
            .ask(text_to_ssml("What would you like to know?"))
            .response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        logger.info("Session ended.")
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Log any unhandled error and speak a message, instead of Alexa's generic
    'the requested skill did not provide a valid response'."""

    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        logger.exception("Unhandled skill error: %s", exception)
        return (
            handler_input.response_builder
            .speak(text_to_ssml(_ERROR))
            .ask(text_to_ssml("What would you like to know?"))
            .response
        )
