"""Utterance frames: the single source of truth for Jarvis's open-ended intents.

Alexa only sends slot values, never the full transcript, and an AMAZON.SearchQuery
slot needs a carrier phrase, at most one per intent, and can't share a sample with
other slots. So each frame is one intent whose carrier phrase IS its `lead`: the
handler rebuilds the user's words as `lead + slot`, e.g. "I prefer tea" ->
IStatementIntent(statement="prefer tea") -> "I prefer tea".

The only extra words a carrier may add are meaning-neutral polite prefixes
("please", "can you", ...), so reconstruction never drops meaning. The interaction
model JSON is generated from this table by scripts/build_interaction_model.py.
"""
from typing import Dict, List, NamedTuple, Optional, Tuple


class Frame(NamedTuple):
    intent: str
    slot: str              # AMAZON.SearchQuery slot name
    lead: str              # spoken carrier phrase; reconstructed text = lead + " " + slot value
    kind: str              # question | request | statement | followup | correction | generic | remember
    polite: Tuple[str, ...] = ("",)   # meaning-neutral prefixes allowed before the lead
    bare: Tuple[str, ...] = ()        # slot-less samples (e.g. "tell me a joke")
    bare_text: Optional[str] = None   # what to send the agent for a bare sample


REQUEST_POLITE = ("", "please ", "can you ", "could you ", "would you ")

_FRAMES: List[Frame] = []


def _add(*frames: Frame) -> None:
    _FRAMES.extend(frames)


def _camel(words: str) -> str:
    """'what's' -> 'Whats', 'tell me a joke about' -> 'TellMeAJokeAbout'."""
    return "".join(w.capitalize() for w in words.replace("'", "").split())


# --- Questions: wh-words, their contractions, and yes/no auxiliaries ------------
for lead in ("what", "what's", "who", "who's", "whose", "where", "where's", "when", "when's",
             "why", "how", "how's", "which"):
    _add(Frame(f"{_camel(lead)}QuestionIntent", "question", lead, "question"))

for lead in ("is", "are", "am", "was", "were", "do", "does", "did", "can", "could", "will",
             "would", "should", "shall", "may", "might", "must", "has", "have", "had",
             "isn't", "aren't", "don't", "doesn't", "didn't", "can't", "won't", "wouldn't",
             "shouldn't"):
    _add(Frame(f"{_camel(lead)}QuestionIntent", "question", lead, "question"))

# --- Requests ---------------------------------------------------------------------
for lead in ("explain", "describe", "define", "compare", "translate", "calculate", "convert",
             "summarize", "recommend", "suggest", "tell me", "give me", "show me", "teach me",
             "help me", "find", "look up", "search for", "give me advice on",
             "give me advice about", "give me tips on"):
    _add(Frame(f"{_camel(lead)}RequestIntent", "request", lead, "request", polite=REQUEST_POLITE))

_add(
    Frame("PleaseRequestIntent", "request", "please", "request"),
    Frame("LetsRequestIntent", "request", "let's", "request"),
    Frame("StoryRequestIntent", "topic", "tell me a story about", "request", polite=REQUEST_POLITE,
          bare=("tell me a story", "tell me a bedtime story"), bare_text="Tell me a short story."),
    Frame("JokeRequestIntent", "topic", "tell me a joke about", "request", polite=REQUEST_POLITE,
          bare=("tell me a joke", "make me laugh", "say something funny"), bare_text="Tell me a joke."),
    Frame("PoemRequestIntent", "topic", "write a poem about", "request", polite=REQUEST_POLITE,
          bare=("write a poem", "write me a poem"), bare_text="Write a short poem."),
)

# --- Statements: facts, preferences and context (NOT saved unless explicitly asked) --
for lead in ("I", "I'm", "I am", "I've", "I have", "I'd", "I would", "my", "we", "our",
             "it's", "that's",
             # spelling a word that speech recognition can't catch: "it's spelled m e h r w e g"
             "it's spelled", "it is spelled", "spelled"):
    _add(Frame(f"{_camel(lead)}StatementIntent", "statement", lead, "statement"))

# --- Follow-ups and corrections ------------------------------------------------------
# "yes/yeah/yep/okay ..." usually answers Jarvis's last question and then continues; a bare
# "yes" has no slot and stays with the built-in AMAZON.YesIntent.
for lead in ("and", "also", "but", "so", "or", "then", "yes", "yeah", "yep", "okay"):
    _add(Frame(f"{_camel(lead)}FollowUpIntent", "followup", lead, "followup"))
for lead in ("actually", "no", "not", "wait", "sorry"):
    _add(Frame(f"{_camel(lead)}CorrectionIntent", "correction", lead, "correction"))

# --- Generic carriers: the slot already holds the whole question ---------------------
GENERIC_CARRIERS = ("ask {query}", "say {query}", "my question is {query}",
                    "here's my question {query}", "question {query}", "jarvis {query}",
                    "tell jarvis {query}", "I want to ask {query}")
_add(Frame("QueryIntent", "query", "", "generic"))

# --- Explicit memory requests: saved to the wiki immediately --------------------------
REMEMBER_CARRIERS = ("remember that {fact}", "remember {fact}", "please remember {fact}",
                     "please remember that {fact}", "can you remember that {fact}",
                     "note that {fact}", "make a note that {fact}", "take a note that {fact}",
                     "save that {fact}", "keep in mind that {fact}", "don't forget that {fact}",
                     "write down that {fact}", "store that {fact}", "memorize that {fact}",
                     "remember this {fact}")
REMEMBER_BARE = ("remember this", "remember something", "save a note", "take a note")
_add(Frame("RememberIntent", "fact", "", "remember", bare=REMEMBER_BARE))

FRAMES: Dict[str, Frame] = {f.intent: f for f in _FRAMES}


def samples(frame: Frame) -> List[str]:
    """Sample utterances for a frame's intent (slot samples first, then bare ones)."""
    if frame.intent == "QueryIntent":
        slotted = list(GENERIC_CARRIERS)
    elif frame.intent == "RememberIntent":
        slotted = list(REMEMBER_CARRIERS)
    else:
        slotted = [f"{p}{frame.lead} {{{frame.slot}}}" for p in frame.polite]
    return slotted + list(frame.bare)


def reconstruct(intent: str, slot_value: Optional[str]) -> Optional[str]:
    """Rebuild the user's words from an intent + slot value; None if nothing usable."""
    frame = FRAMES[intent]
    value = (slot_value or "").strip()
    if not value:
        return frame.bare_text
    if frame.kind == "correction":
        return f"Correction to what I said before: {frame.lead} {value}"
    return f"{frame.lead} {value}".strip()
