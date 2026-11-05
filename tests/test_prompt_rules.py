"""Rules in the agent's system prompt: answer grounding, yes-style continuations, and
general recovery for German words that Alexa's English speech recognition garbles."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import agent

PROMPT = agent._SYSTEM_PROMPT
LOWER = PROMPT.lower()


def test_prompt_forbids_talking_about_tools():
    import agent as agent_module
    assert "don't mention searching" in agent_module._SYSTEM_PROMPT.lower()


def test_prompt_requires_a_source_for_money_and_legal_claims_not_just_amounts():
    import agent as agent_module
    prompt = agent_module._SYSTEM_PROMPT.lower()
    for phrase in ("deposits", "what a law or regulation requires",
                   "whether something has a fee or deposit at all", "costs more or less",
                   "must come from a search_web result in this conversation",
                   "if the question doesn't need such a claim, leave it out"):
        assert phrase in prompt, phrase


def test_prompt_limits_answers_to_what_was_asked():
    import agent as agent_module
    assert "answer only what was asked" in agent_module._SYSTEM_PROMPT.lower()


def test_prompt_keeps_definitions_and_differences_free_of_money_details():
    import agent as agent_module
    prompt = agent_module._SYSTEM_PROMPT.lower()
    assert "'what is the difference' question" in prompt and "don't add money, price, deposit or legal details" in prompt


def test_prompt_explains_yes_prefixed_messages():
    import agent as agent_module
    assert "starting with 'yes', 'yeah', 'yep' or 'okay'" in agent_module._SYSTEM_PROMPT


# --- general German recovery (no word lists) --------------------------------------------------

def test_garbled_text_is_treated_as_a_possible_german_word_and_only_as_a_guess():
    assert "english-sounding words" in LOWER
    assert "treat any german word you infer from the sound as a guess, not a fact" in LOWER


def test_guess_needs_a_confirmation_before_answering_or_searching():
    assert "before answering, ask one short confirmation" in LOWER
    assert "don't search for or answer about a guessed word until the user confirms it" in LOWER


def test_no_guess_means_repeat_or_spell():
    assert "ask the user to repeat the word or spell it" in LOWER
    assert "join the letters into the word" in LOWER


def test_confirmation_replies_use_the_conversation():
    assert "a reply of yes, no, or a correction refers to that question" in LOWER


def test_clean_german_and_ordinary_english_need_no_confirmation():
    assert "german words that came through correctly need no confirmation" in LOWER
    assert "ordinary english words keep their english meaning" in LOWER
    assert "never assume an english word is a misheard german word without asking" in LOWER


def test_prompt_never_promises_to_know_every_german_word_and_has_no_word_list():
    for word in ("mehrwegflasche", "pfand", "fondue ->", "font ->"):
        assert word not in LOWER


def test_reply_is_spoken_verbatim_so_no_reasoning_is_written():
    assert "your reply is spoken aloud word for word" in LOWER
    assert "never your reasoning" in LOWER


def test_bare_yes_or_no_only_answers_the_immediately_previous_reply():
    assert "a bare yes or no answers only your immediately previous reply" in LOWER


def test_saving_needs_the_users_explicit_words_and_a_bare_yes_is_not_enough():
    assert "a bare yes is not enough" in LOWER
