from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.api_client import DefaultApiClient

from intent_handlers import (
    LaunchRequestHandler,
    QueryIntentHandler,
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
)

# CustomSkillBuilder (not SkillBuilder) is required to enable
# the directive service used for progressive responses.
sb = CustomSkillBuilder(api_client=DefaultApiClient())

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(QueryIntentHandler())
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

lambda_handler = sb.lambda_handler()
