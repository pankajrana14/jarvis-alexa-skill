import logging
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.services.directive import SendDirectiveRequest, Header, SpeakDirective

from agent import run_agent
from wiki_manager import WikiManager
from ssml_builder import text_to_ssml, clean_for_speech

logger = logging.getLogger(__name__)

# Module-level wiki index cache — persists across warm Lambda invocations
_wiki_index_cache: str = ""

_WELCOME = "Hi, I'm Jarvis. What would you like to know?"
_HELP = "You can ask me anything. Just say your question. Say stop to exit."
_STOP = "Goodbye!"
_FALLBACK = "Sorry, I didn't catch that. What would you like to know?"
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
    wiki_index = _wiki_index_cache

    agent_error = False
    try:
        response_text = run_agent(query, history, wiki_index, wiki_manager)
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


class QueryIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("QueryIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        slots = handler_input.request_envelope.request.intent.slots
        query_slot = slots.get("query") if slots else None
        query = query_slot.value if query_slot and query_slot.value else None

        if not query:
            return (
                handler_input.response_builder
                .speak(text_to_ssml(_FALLBACK))
                .ask(text_to_ssml("What would you like to know?"))
                .response
            )

        return _handle_query(handler_input, query)


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
        return _handle_query(handler_input, "Yes, please go ahead.")


class NoIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.NoIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder
            .speak(text_to_ssml("Okay, let me know if there's anything else."))
            .ask(text_to_ssml("Is there anything else?"))
            .response
        )


class StopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return (
            is_intent_name("AMAZON.StopIntent")(handler_input)
            or is_intent_name("AMAZON.CancelIntent")(handler_input)
        )

    def handle(self, handler_input: HandlerInput) -> Response:
        return handler_input.response_builder.speak(text_to_ssml(_STOP)).response


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
