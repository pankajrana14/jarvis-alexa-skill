#!/usr/bin/env python3
"""
Generate skill-package/interactionModels/custom/en-US.json from utterance_frames.py.

Run from the jarvis/ directory: python scripts/build_interaction_model.py
Then paste the file into Alexa developer console -> Build -> JSON Editor -> Save -> Build skill.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utterance_frames import FRAMES, samples  # noqa: E402

OUT = ROOT / "skill-package" / "interactionModels" / "custom" / "en-US.json"

# Fixed-phrase intents (no slot). Kept from the original model.
FIXED_INTENTS = {
    "PriceQueryIntent": [
        "how much does it cost", "what is the price", "how expensive is it", "what does it cost",
        "and the price", "how much does that cost", "what's the price", "is it expensive",
    ],
    "MoreDetailsIntent": [
        "tell me more", "what else", "give me more details", "more information", "elaborate",
        "go on", "and what else", "tell me more about it", "anything else", "keep going",
        "continue", "and then what", "what else should I know",
    ],
    "GreetingIntent": [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening", "how are you",
        "how are you doing", "what's up", "hey jarvis",
    ],
    "ThankYouIntent": [
        "thank you", "thanks", "thank you so much", "thanks a lot", "that's helpful",
        "that was helpful", "great", "awesome", "perfect", "got it", "okay thanks", "cheers",
    ],
}
BUILTINS = {
    "AMAZON.StopIntent": ["stop", "goodbye", "exit", "quit", "bye", "that's all", "see you", "farewell"],
    "AMAZON.YesIntent": [],
    "AMAZON.NoIntent": [],
    "AMAZON.CancelIntent": [],
    "AMAZON.HelpIntent": [],
    "AMAZON.FallbackIntent": [],
    "AMAZON.NavigateHomeIntent": [],
}

# Intents that exist only in the Alexa console (added there by hand or by the console)
# and must survive regeneration: put their JSON objects in this list file.
EXTRA_INTENTS_FILE = OUT.parent / "console_extra_intents.json"


def _extra_intents() -> list:
    if not EXTRA_INTENTS_FILE.exists():
        return []
    return json.loads(EXTRA_INTENTS_FILE.read_text(encoding="utf-8"))


def build() -> dict:
    intents = []
    for frame in FRAMES.values():
        intents.append({
            "name": frame.intent,
            "slots": [{"name": frame.slot, "type": "AMAZON.SearchQuery"}],
            "samples": samples(frame),
        })
    for name, utterances in FIXED_INTENTS.items():
        intents.append({"name": name, "slots": [], "samples": utterances})
    for name, utterances in BUILTINS.items():
        intents.append({"name": name, "samples": utterances})
    known = {i["name"] for i in intents}
    for extra in _extra_intents():
        if extra["name"] in known:
            raise SystemExit(f"{EXTRA_INTENTS_FILE.name}: {extra['name']} is already generated; remove it there")
        intents.append(extra)
    return {
        "interactionModel": {
            "languageModel": {
                "invocationName": "jarvis",
                # LOW: route borderline utterances to our intents rather than to fallback.
                "modelConfiguration": {"fallbackIntentSensitivity": {"level": "LOW"}},
                "intents": intents,
                "types": [],
            }
        }
    }


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8", newline="\n")
    model = build()["interactionModel"]["languageModel"]
    n_samples = sum(len(i.get("samples", [])) for i in model["intents"])
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(model['intents'])} intents, {n_samples} samples, "
          f"{OUT.stat().st_size / 1024:.0f} KB")
