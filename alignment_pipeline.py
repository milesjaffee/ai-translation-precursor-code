"""
Example redesign of the annotated-alignment pipeline.

Core idea: never ask the model to invent an index that hasn't been
generated yet. Tokenization and numbering happen in plain Python
(deterministic, free, instant, and can't be "lazy"). The model is only
ever asked to point at numbers it can already see in front of it, and
schemas are built per-request so an impossible field (e.g. 'latin' on
a Latin-script side) is not just discouraged in the prompt -- it's
structurally absent from the grammar, so it literally cannot be
emitted.
"""

import json
import regex
import re
from typing import List, Optional, Type
from pydantic import BaseModel, Field, create_model
import icu
import pysbd

from few_shot_examples import FEW_SHOT_EXAMPLES

LATIN_SCRIPT_LANGS = {"en", "es", "fr", "de", "it", "pt", "tr", "nl", "sv", "id", "vi"}
NO_SPACE_SCRIPTS = {"zh", "ja", "th", "lo", "km", "my"}

# ---------------------------------------------------------------------
# 1. Deterministic tokenization -- do this in code, not in the model.
# ---------------------------------------------------------------------


# Numbers with internal punctuation stay one token (5,461 / 5.461);
# letter runs are one token; every other symbol is its own token.
_WORD_OR_PUNCT = regex.compile(r"\p{N}+(?:[.,]\p{N}+)*|\p{L}+|[^\s\p{L}\p{N}]")

def tokenize(text: str, lang: str) -> list[str]:
    if lang == "lzh":
        # Literary/Classical Chinese: words are (almost) always a single
        # character, unlike Modern Mandarin's frequent multi-character
        # compounds -- e.g. 非常 is one word ("very") in modern zh but
        # two ("not" + "eternal") in classical text. ICU's word breaker
        # is trained on modern usage and would wrongly merge these, so
        # skip it and just split per character.
        return [ch for ch in text if not ch.isspace()]

    if lang not in NO_SPACE_SCRIPTS:
        return _WORD_OR_PUNCT.findall(text)

    bi = icu.BreakIterator.createWordInstance(icu.Locale(lang))
    bi.setText(text)
    tokens, start = [], bi.first()
    for end in bi:
        piece = text[start:end]
        if piece.strip():   # ICU also yields whitespace-only breaks — skip them
            tokens.append(piece)
        start = end
    return tokens


def numbered_list(tokens: List[str]) -> str:
    """Render a 1-indexed list the model can read AND copy indices from."""
    return "\n".join(f"{i + 1}. {tok}" for i, tok in enumerate(tokens))


# ---------------------------------------------------------------------
# 2. Per-request schema -- exclude 'latin' entirely for Latin-script
#    languages instead of just telling the model not to use it.
# ---------------------------------------------------------------------


def word_annotation_model(needs_latin: bool) -> Type[BaseModel]:
    """Build a WordAnnotation model with or without the 'latin' field.

    Note this deliberately does NOT include 'word' -- you already know
    the word text from your own tokenizer, so there's no reason to make
    the model regenerate (and potentially desync from) it.
    """
    fields = {
        "meaning": (List[str], Field(..., description="Meanings in the other language.")),
        "opposite_translation_index": (List[int], Field(..., description="Indexes of corresponding word(s) on the OTHER side.")),
        "footnote": (Optional[str], Field(default=None)),
    }
    if needs_latin:
        fields["latin"] = (str, Field(..., description="Latin-alphabet transcription, e.g. pinyin."))
    return create_model("WordAnnotation", **fields)


def alignment_schema(source_lang: str, target_lang: str, source_count: int, target_count: int) -> Type[BaseModel]:
    """Build the Alignment model for one sentence pair.

    source_count/target_count pin minItems == maxItems == the actual
    token count on each side, so the model's JSON grammar structurally
    cannot emit a source/translation array shorter or longer than the
    tokens it's annotating -- there's no valid output where recombining
    by position (see align_and_annotate) could run out of entries.
    """
    SourceWord = word_annotation_model(source_lang not in LATIN_SCRIPT_LANGS)
    TargetWord = word_annotation_model(target_lang not in LATIN_SCRIPT_LANGS)
    return create_model(
        "Alignment",
        source=(List[SourceWord], Field(..., min_length=source_count, max_length=source_count)),
        translation=(List[TargetWord], Field(..., min_length=target_count, max_length=target_count)),
    )


# ---------------------------------------------------------------------
# 3. Sentence-chunked, multishot alignment + annotation.
# ---------------------------------------------------------------------
# Both numbered token lists are ALREADY in the prompt before the model
# writes a single output token, so 'match' is a copy task ("point at a
# number you can see") instead of a generation task ("invent a number
# for content you haven't written yet"). This is the actual fix for
# the "lazy incrementing counter" behavior.
#
# If reliability is still shaky once this is in place, split further:
# do a call that ONLY returns match arrays (minimal schema, cheapest
# possible generation), then a second call for meaning/latin/footnote,
# which don't need cross-referencing at all and are easy on their own.
#
# Small models also lose the plot over long structured outputs, so
# alignment happens sentence-by-sentence and results are merged in
# code -- each call stays small, and one bad sentence doesn't cascade
# into a wrong global offset for every sentence after it. Sentence
# calls share one growing conversation ("multishot") rather than each
# starting fresh: every earlier sentence's prompt and the model's own
# answer to it stay in context, so later sentences get real in-context
# examples of the JSON format and of how recurring words were aligned,
# instead of the model re-deciding conventions from scratch each time.

def build_alignment_prompt(source_tokens, target_tokens, source_lang, target_lang):
    return (
        f"SOURCE ({source_lang}), numbered:\n{numbered_list(source_tokens)}\n\n"
        f"TRANSLATION ({target_lang}), numbered:\n{numbered_list(target_tokens)}\n\n"
        "For every source word, list the index/indexes of the "
        "word(s) it corresponds to in the OPPOSITE side, NOT ITS OWN INDEX, and vice versa. Only use the numbers "
        "shown above. A word's match should reflect actual meaning "
        "correspondence -- do not default to a word's own "
        "index or a running count unless that genuinely is the correct "
        "correspondence at that point. You are being graded and will be harshly penalized for matching the index to its own index."
    )


def split_sentences(text: str, lang: str):
    """Split text into sentences using pysbd, which is language-aware."""
    seg = pysbd.Segmenter(language=lang, clean=False)
    return seg.segment(text)


def few_shot_messages():
    """Render FEW_SHOT_EXAMPLES as fixed user/assistant turns.

    Tokenizing here (rather than hand-listing tokens) means the prompt
    side always matches whatever the current tokenize()/numbered_list()
    actually produce, even if tokenization rules change later.
    """
    turns = []
    for ex in FEW_SHOT_EXAMPLES:
        source_tokens = tokenize(ex["source_text"], ex["source_lang"])
        target_tokens = tokenize(ex["target_text"], ex["target_lang"])
        prompt = build_alignment_prompt(source_tokens, target_tokens, ex["source_lang"], ex["target_lang"])
        answer = {"source": ex["source_annotations"], "translation": ex["target_annotations"]}
        turns.append({"role": "user", "content": prompt})
        turns.append({"role": "assistant", "content": json.dumps(answer)})
    return turns


def align_and_annotate(model, source_text, target_text, source_lang, target_lang, history_window=None):
    """Align and annotate a document sentence-by-sentence.

    history_window caps how many prior sentence turns (user+assistant
    pairs) stay in the conversation, on top of the system message.
    None keeps the whole document's history (default); 0 makes every
    sentence call independent, since only the system message remains.
    """
    # NOTE: splitting source and translation independently only works
    # if they have the same number of sentences in the same order. For
    # real use, it's safer to have the translation step itself preserve
    # sentence boundaries (one sentence in -> one sentence out) so this
    # pairing is guaranteed rather than assumed.
    src_sents = split_sentences(source_text, source_lang)
    tgt_sents = split_sentences(target_text, target_lang)
    assert len(src_sents) == len(tgt_sents), "sentence counts diverged between source and translation"

    messages = [
        {"role": "system", "content": "You are an expert translator and linguist doing word-level alignment."},
    ]
    messages.extend(few_shot_messages())

    src_offset = tgt_offset = 0
    combined_source, combined_translation = [], []
    for s_sent, t_sent in zip(src_sents, tgt_sents):
        source_tokens = tokenize(s_sent, source_lang)
        target_tokens = tokenize(t_sent, target_lang)

        # Built per-sentence, not once per document: minItems/maxItems
        # must match THIS sentence's token counts (see alignment_schema).
        schema = alignment_schema(source_lang, target_lang, len(source_tokens), len(target_tokens))
        response_format = {"type": "json_object", "schema": schema.model_json_schema()}

        alignment_prompt = build_alignment_prompt(source_tokens, target_tokens, source_lang, target_lang)
        messages.append({"role": "user", "content": alignment_prompt})

        result = model.create_chat_completion(messages=messages, response_format=response_format)
        content = result["choices"][0]["message"]["content"]
        messages.append({"role": "assistant", "content": content})
        if history_window is not None:
            kept_turns = messages[-2 * history_window:] if history_window > 0 else []
            messages = [messages[0]] + kept_turns

        parsed = json.loads(content)

        # Recombine model output (meaning/match/latin/footnote) with the
        # words YOU already know, by position. The model never had to echo
        # the word text back, so there's no way for it to drift out of sync
        # with its own numbering.
        for i, tok in enumerate(source_tokens):
            parsed["source"][i]["word"] = tok
        for i, tok in enumerate(target_tokens):
            parsed["translation"][i]["word"] = tok

        for w in parsed["source"]:
            w["opposite_translation_index"] = [m + tgt_offset for m in w["opposite_translation_index"]]
        for w in parsed["translation"]:
            w["opposite_translation_index"] = [m + src_offset for m in w["opposite_translation_index"]]
        combined_source.extend(parsed["source"])
        combined_translation.extend(parsed["translation"])
        src_offset += len(parsed["source"])
        tgt_offset += len(parsed["translation"])

    return {"source": combined_source, "translation": combined_translation}
