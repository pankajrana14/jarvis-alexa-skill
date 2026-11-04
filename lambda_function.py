import logging

import config

# Must run before the handlers import: on Alexa-hosted skills the API keys
# come from a bundled .env, since Lambda env vars can't be edited there.
config.load_bundled_env()

logging.getLogger().setLevel(logging.INFO)

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.api_client import DefaultApiClient

from intent_handlers import (
    LaunchRequestHandler,
    UtteranceIntentHandler,
    RememberIntentHandler,
    PriceQueryIntentHandler,
    MoreDetailsIntentHandler,
    GreetingIntentHandler,
    ThankYouIntentHandler,
    YesIntentHandler,
    NoIntentHandler,
    StopIntentHandler,
    HelpIntentHandler,
    FallbackIntentHandler,
    SessionEndedRequestHandler,
    CatchAllExceptionHandler,
)

# CustomSkillBuilder (not SkillBuilder) is required to enable
# the directive service used for progressive responses.
sb = CustomSkillBuilder(api_client=DefaultApiClient())

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(RememberIntentHandler())
sb.add_request_handler(UtteranceIntentHandler())
sb.add_request_handler(PriceQueryIntentHandler())
sb.add_request_handler(MoreDetailsIntentHandler())
sb.add_request_handler(GreetingIntentHandler())
sb.add_request_handler(ThankYouIntentHandler())
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(NoIntentHandler())
sb.add_request_handler(StopIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_exception_handler(CatchAllExceptionHandler())

lambda_handler = sb.lambda_handler()
