"""Validates the generated Alexa interaction model against Amazon's rules and our
reconstruction invariant (carrier phrase == frame lead, plus polite prefixes only)."""
import sys, os, re, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from collections import Counter
from pathlib import Path

import build_interaction_model as gen
from utterance_frames import FRAMES, GENERIC_CARRIERS, REMEMBER_CARRIERS, samples

MODEL_PATH = Path(__file__).resolve().parent.parent / "skill-package/interactionModels/custom/en-US.json"
LM = json.loads(MODEL_PATH.read_text(encoding="utf-8"))["interactionModel"]["languageModel"]
INTENTS = {i["name"]: i for i in LM["intents"]}
ALL_SAMPLES = [s for i in LM["intents"] for s in i.get("samples", [])]
SLOT_RE = re.compile(r"\{(\w+)\}")


def test_committed_model_is_exactly_the_generated_one():
    assert MODEL_PATH.read_text(encoding="utf-8") == gen.render(), \
        "en-US.json is stale: run python scripts/build_interaction_model.py"


def test_samples_are_unique_across_all_intents():
    dupes = [s for s, n in Counter(s.lower() for s in ALL_SAMPLES).items() if n > 1]
    assert not dupes


def test_samples_follow_amazon_text_rules():
    # words as letters, apostrophes for contractions, braces for slots; no digits or other punctuation
    bad = [s for s in ALL_SAMPLES if not re.fullmatch(r"[A-Za-z' {}]+", s)]
    assert not bad


def test_search_query_rules():
    for intent in LM["intents"]:
        slots = intent.get("slots", [])
        search = [s for s in slots if s["type"] == "AMAZON.SearchQuery"]
        assert len(search) <= 1, intent["name"]
        if search:
            assert len(slots) == 1, f"{intent['name']}: SearchQuery can't share a sample with other slots"
        for sample in intent.get("samples", []):
            used = SLOT_RE.findall(sample)
            assert len(used) <= 1, sample
            if used:
                assert used[0] in {s["name"] for s in slots}, sample
                carrier = SLOT_RE.sub("", sample).strip()
                assert carrier, f"{intent['name']}: '{sample}' has no carrier phrase"


def test_every_frame_carrier_is_its_lead_so_reconstruction_keeps_the_words():
    for frame in FRAMES.values():
        if frame.kind in ("generic", "remember"):
            continue
        for sample in samples(frame):
            if "{" not in sample:
                continue
            assert sample.endswith(f"{frame.lead} {{{frame.slot}}}"), sample
            prefix = sample[: -len(f"{frame.lead} {{{frame.slot}}}")]
            assert prefix in frame.polite, f"{sample!r}: '{prefix}' is not a meaning-neutral prefix"


def test_required_carriers_and_families_are_covered():
    for carrier in ("say {query}", "ask {query}", "my question is {query}"):
        assert carrier in GENERIC_CARRIERS
    assert "remember that {fact}" in REMEMBER_CARRIERS
    leads = {f.lead for f in FRAMES.values()}
    for lead in ("what", "what's", "who", "where", "when", "why", "how", "which",   # wh questions
                 "is", "are", "can", "do", "does", "did", "will", "should",          # yes/no
                 "explain", "compare", "translate", "calculate", "give me advice on",  # requests
                 "tell me a story about", "tell me a joke about", "write a poem about",
                 "I", "I'm", "my",                                                   # statements
                 "and", "actually", "no"):                                           # follow-ups
        assert lead in leads, lead


def test_fallback_and_limits():
    assert LM["invocationName"] == "jarvis"
    assert LM["modelConfiguration"]["fallbackIntentSensitivity"]["level"] == "LOW"
    assert "AMAZON.FallbackIntent" in INTENTS
    assert len(INTENTS) <= 250
    assert MODEL_PATH.stat().st_size < 1.5 * 1024 * 1024
    # no standalone slot-only samples anywhere
    assert not [s for s in ALL_SAMPLES if SLOT_RE.fullmatch(s.strip())]
