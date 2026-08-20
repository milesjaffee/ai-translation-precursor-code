"""
Example redesign of the annotated-alignment pipeline (v2).

Changes from v1:
  - Generic tokenizer that also handles CJK/Thai/etc. via ICU word
    boundaries, instead of a whitespace-only regex.
  - Sentence chunking is no longer a naive regex split + strict zip.
    It's a small LLM call that GROUPS source/translation sentences
    (allowing merges, splits, insertions, deletions), the same way
    word-level alignment groups words -- because the same forward-
    reference logic applies at the sentence level, and a strict zip
    breaks the moment a translator merges or reorders sentences.
  - Few-shot examples for both calls are reused from your worked
    daodejing1 / spanish_joke examples, adapted to the new narrow
    schemas and re-tokenized to a conventional "every punctuation
    mark is its own token" scheme.

Install: pip install PyICU regex
(PyICU needs the system ICU library present; on most Linux distros
`apt install libicu-dev` first. regex is the third-party `regex`
package, not stdlib re -- it supports \\p{...} unicode properties.)
"""

import json
import regex  # pip install regex
import icu    # pip install PyICU
from typing import List, Optional, Type
from pydantic import BaseModel, Field, create_model


# =======================================================================
# 1. TOKENIZATION -- generic, handles space-delimited scripts and CJK.
# =======================================================================

LATIN_SCRIPT_LANGS = {"en", "es", "fr", "de", "it", "pt", "tr", "nl", "sv", "id", "vi", "pl", "ro", "hu", "da", "fi", "no", "cs", "sk", "sl", "hr", "lt", "lv", "et"}

# Scripts that don't use whitespace between words at all.
NO_SPACE_SCRIPTS = {"zh", "ja", "th", "lo", "km", "my"}

# Numbers with internal punctuation stay one token (5,461 / 5.461);
# letter runs are one token; every other symbol is its own token.
# This gives you the "conventional" punctuation-per-token behavior for
# any space-delimited script for free, including splitting contractions
# at the apostrophe ("I've" -> "I", "'", "ve") since apostrophe isn't a
# letter. If you'd rather keep contractions glued together, special-case
# that here -- it's a defensible choice either way, just pick one and
# make the few-shot examples match it (see section 4).
_WORD_OR_PUNCT = regex.compile(r"\p{N}+(?:[.,]\p{N}+)*|\p{L}+|[^\s\p{L}\p{N}]")


def tokenize(text: str, lang: str, cjk_granularity: str = "dictionary") -> List[str]:
    """Tokenize `text`. cjk_granularity only matters for NO_SPACE_SCRIPTS:

    - "dictionary": ICU's built-in word-break dictionary (good for
      modern text, groups multi-character words like "非常").
    - "char": one token per character. Safer default for classical /
      literary text, where a modern segmenter's word groupings can be
      anachronistic -- e.g. splitting "非常道" into modern "非常"
      ("extremely") + "道" would be WRONG for the Daodejing, which is
      using the archaic compositional reading ("not" + "constant" +
      "way"), not the modern compound. When in doubt for old or
      ambiguous text, "char" is the safer choice; you can always merge
      characters back into compounds manually where you're confident.
    """
    if lang not in NO_SPACE_SCRIPTS:
        return _WORD_OR_PUNCT.findall(text)

    if cjk_granularity == "char":
        return [ch for ch in text if not ch.isspace()]

    bi = icu.BreakIterator.createWordInstance(icu.Locale(lang))
    bi.setText(text)
    tokens, start = [], bi.first()
    for end in bi:
        piece = text[start:end]
        if piece.strip():  # ICU also yields whitespace-only breaks -- skip
            tokens.append(piece)
        start = end
    return tokens


def numbered_list(tokens: List[str]) -> str:
    return "\n".join(f"{i + 1}. {tok}" for i, tok in enumerate(tokens))


# =======================================================================
# 2. SENTENCE SEGMENTATION -- ICU sentence breaks, not a regex lookbehind.
# =======================================================================
# A [.!?]-based regex breaks on "Mr. Smith", "e.g.", decimals, ellipses,
# initials, etc. ICU's sentence-break iterator carries locale-specific
# abbreviation exceptions and is a real improvement, though still not
# perfect on every edge case. (PySBD is another option, tuned harder
# specifically for English/European abbreviation handling, if you find
# ICU still mis-splitting too often on your text.)

def segment_sentences(text: str, lang: str) -> List[str]:
    bi = icu.BreakIterator.createSentenceInstance(icu.Locale(lang))
    bi.setText(text)
    sents, start = [], bi.first()
    for end in bi:
        piece = text[start:end].strip()
        if piece:
            sents.append(piece)
        start = end
    return sents


# =======================================================================
# 3. PER-REQUEST SCHEMA -- 'latin' structurally absent where it can't apply.
# =======================================================================

def word_annotation_model(needs_latin: bool) -> Type[BaseModel]:
    """WordAnnotation model. Deliberately excludes 'word' -- you already
    know the word text from your own tokenizer, so the model is never
    asked to regenerate (and potentially desync from) it.
    """
    fields = {
        "meaning": (List[str], Field(..., description="Meanings in the other language.")),
        "match": (List[int], Field(..., description="Indexes of corresponding word(s) on the OTHER side.")),
        "footnote": (Optional[str], Field(default=None)),
    }
    if needs_latin:
        fields["latin"] = (
            Optional[str],
            Field(default=None, description="Latin-alphabet transcription; null if there's nothing to transcribe (e.g. punctuation, numerals)."),
        )
    return create_model("WordAnnotation", **fields)


def alignment_schema(source_lang: str, target_lang: str, num_source: int, num_target: int) -> Type[BaseModel]:
    """`num_source`/`num_target` pin exact array lengths (minItems == maxItems
    == token count) so the grammar-constrained decoder can't return a
    source/translation list shorter or longer than the tokens it's meant to
    annotate one-for-one -- which otherwise produces an output that desyncs
    from the token list it's zipped against in align_and_annotate.
    """
    SourceWord = word_annotation_model(source_lang not in LATIN_SCRIPT_LANGS)
    TargetWord = word_annotation_model(target_lang not in LATIN_SCRIPT_LANGS)
    return create_model(
        "Alignment",
        source=(List[SourceWord], Field(..., min_length=num_source, max_length=num_source)),
        translation=(List[TargetWord], Field(..., min_length=num_target, max_length=num_target)),
    )


class SentenceGroup(BaseModel):
    source: List[int] = Field(..., description="1-based source sentence indices in this group. Empty if this group is a pure insertion (nothing on the source side).")
    translation: List[int] = Field(..., description="1-based translation sentence indices in this group. Empty if the source sentence(s) were dropped/untranslated.")


class SentenceGrouping(BaseModel):
    groups: List[SentenceGroup] = Field(..., description="Groups IN ORDER, covering every sentence on both sides exactly once.")


# =======================================================================
# 4. FEW-SHOT DATA -- your worked examples, re-tokenized + reshaped.
# =======================================================================
# Re-tokenized to "every punctuation mark is its own token" and reshaped
# to the new narrow schema (no 'word' field; 'latin' key absent entirely
# for Latin-script sides rather than present-but-null). The content and
# the underlying linguistic judgment calls are the same as your originals
# -- only the token boundaries and output shape changed.

DAODEJING_SOURCE_WORDS = ["道", "可", "道", "，", "非", "常", "道"]
DAODEJING_TARGET_WORDS = ["The", "Way", "that", "can", "be", "spoken", "of", "is", "not", "the", "eternal", "Way"]
DAODEJING_SOURCE_ANNOT = [
    {"meaning": ["The Tao", "way", "path", "to speak", "to guide"], "match": [1, 2], "latin": "dào", "footnote": None},
    {"meaning": ["can", "may", "able to"], "match": [3, 4], "latin": "kě", "footnote": None},
    {"meaning": ["The Tao", "way", "path", "to speak", "to guide"], "match": [5, 6, 7], "latin": "dào", "footnote": None},
    {"meaning": [], "match": [], "latin": None, "footnote": None},  # ，  -- punctuation, nothing to transcribe
    {"meaning": ["not", "non-", "un-"], "match": [8, 9], "latin": "fēi", "footnote": None},
    {"meaning": ["eternal", "constant", "unchanging"], "match": [10, 11], "latin": "cháng", "footnote": None},
    {"meaning": ["The Tao", "way", "path", "to speak", "to guide"], "match": [12], "latin": "dào", "footnote": None},
]
DAODEJING_TARGET_ANNOT = [
    {"meaning": [], "match": [], "footnote": None},                                   # The
    {"meaning": ["道"], "match": [1], "footnote": None},                               # Way
    {"meaning": [], "match": [], "footnote": None},                                   # that
    {"meaning": ["可", "能"], "match": [2], "footnote": None},                          # can
    {"meaning": [], "match": [], "footnote": None},                                   # be
    {"meaning": ["言"], "match": [3], "footnote": "Note that the same character is used for both 'way' and 'to speak', making the direct translation ambiguous."},  # spoken
    {"meaning": [], "match": [], "footnote": None},                                   # of
    {"meaning": [], "match": [], "footnote": None},                                   # is
    {"meaning": ["不"], "match": [5], "footnote": None},                               # not
    {"meaning": [], "match": [], "footnote": None},                                   # the
    {"meaning": ["常"], "match": [6], "footnote": None},                               # eternal
    {"meaning": ["道"], "match": [7], "footnote": None},                               # Way
]

SPANISH_JOKE_SOURCE_WORDS = ["¡", "Socorro", ",", "me", "ha", "picado", "una", "víbora", "!", "¿", "Cobra", "?", "No", ",", "gratis", "."]
SPANISH_JOKE_TARGET_WORDS = ["Help", "!", "I", "'", "ve", "been", "bitten", "by", "a", "viper", "!", "Does", "it", "cost", "money", "?", "No", ",", "it", "'", "s", "free", "."]
SPANISH_JOKE_SOURCE_ANNOT = [
    {"meaning": [], "match": [], "footnote": None},                                                                  # ¡
    {"meaning": ["Help!"], "match": [1], "footnote": None},                                                          # Socorro
    {"meaning": [], "match": [], "footnote": None},                                                                  # ,
    {"meaning": ["me", "myself"], "match": [3], "footnote": None},                                                   # me
    {"meaning": ["has"], "match": [5], "footnote": None},                                                            # ha
    {"meaning": ["bitten", "stung"], "match": [7], "footnote": None},                                                # picado
    {"meaning": ["a", "one"], "match": [9], "footnote": None},                                                       # una
    {"meaning": ["viper", "snake"], "match": [10], "footnote": None},                                                # víbora
    {"meaning": [], "match": [], "footnote": None},                                                                  # !
    {"meaning": [], "match": [], "footnote": None},                                                                  # ¿
    {"meaning": ["Cobra?", "Does it cost money?"], "match": [12, 13, 14, 15], "footnote": "This is a pun -- 'cobra' can mean both 'Cobra' (the snake) and 'Does it cost money?' in Spanish."},  # Cobra
    {"meaning": [], "match": [], "footnote": None},                                                                  # ?
    {"meaning": ["No,"], "match": [17], "footnote": None},                                                           # No
    {"meaning": [], "match": [], "footnote": None},                                                                  # ,
    {"meaning": ["free", "gratis"], "match": [22], "footnote": None},                                                # gratis
    {"meaning": [], "match": [], "footnote": None},                                                                  # .
]
SPANISH_JOKE_TARGET_ANNOT = [
    {"meaning": ["¡Socorro!", "¡Ayuda!"], "match": [2], "footnote": None},   # Help
    {"meaning": [], "match": [], "footnote": None},                         # !
    {"meaning": ["me"], "match": [4], "footnote": None},                    # I
    {"meaning": [], "match": [], "footnote": None},                        # '
    {"meaning": ["ha"], "match": [5], "footnote": None},                    # ve
    {"meaning": ["ha"], "match": [5], "footnote": None},                    # been
    {"meaning": ["picado"], "match": [6], "footnote": None},                # bitten
    {"meaning": ["por"], "match": [], "footnote": None},                    # by
    {"meaning": ["una"], "match": [7], "footnote": None},                   # a
    {"meaning": ["víbora"], "match": [8], "footnote": None},                # viper
    {"meaning": [], "match": [], "footnote": None},                        # !
    {"meaning": [], "match": [11], "footnote": None},                      # Does
    {"meaning": [], "match": [11], "footnote": None},                      # it
    {"meaning": ["cobra"], "match": [11], "footnote": None},                # cost
    {"meaning": ["dinero"], "match": [11], "footnote": None},               # money
    {"meaning": [], "match": [], "footnote": None},                        # ?
    {"meaning": ["No"], "match": [13], "footnote": None},                   # No
    {"meaning": [], "match": [], "footnote": None},                        # ,
    {"meaning": [], "match": [], "footnote": None},                        # it
    {"meaning": [], "match": [], "footnote": None},                        # '
    {"meaning": [], "match": [], "footnote": "Spanish elides the copula here -- 'No, gratis' literally reads 'No, free,' with 'it is' left implicit."},  # s
    {"meaning": ["gratis"], "match": [15], "footnote": None},               # free
    {"meaning": [], "match": [], "footnote": None},                        # .
]

# Sentence-grouping few-shot examples. The MERGE example is listed first
# and is not optional: if every grouping example you show is 1:1, a small
# model will learn to always emit 1:1 groups, which defeats the entire
# purpose of grouping instead of zipping. At least one genuine merge/
# split example belongs in this set; add a split example too for a real
# deployment, this is a minimal illustrative set.
GROUPING_EXAMPLES = [
    {
        "source_sents": ["It started raining.", "We went inside."],
        "target_sents": ["Como empezó a llover, entramos."],
        "source_lang": "en", "target_lang": "es",
        "groups": [{"source": [1, 2], "translation": [1]}],
    },
    {
        "source_sents": ["¡Socorro, me ha picado una víbora!", "¿Cobra?", "No, gratis."],
        "target_sents": ["Help! I've been bitten by a viper!", "Does it cost money?", "No, it's free."],
        "source_lang": "es", "target_lang": "en",
        "groups": [{"source": [1], "translation": [1]}, {"source": [2], "translation": [2]}, {"source": [3], "translation": [3]}],
    },
]


# =======================================================================
# 5. WORD-LEVEL ALIGNMENT CALL.
# =======================================================================

def build_alignment_prompt(source_tokens, target_tokens, source_lang, target_lang, context=""):
    ctx = f"Surrounding context (for meaning/footnotes only -- do NOT index into this):\n{context}\n\n" if context else ""
    return (
        f"{ctx}"
        f"SOURCE ({source_lang}), numbered:\n{numbered_list(source_tokens)}\n\n"
        f"TRANSLATION ({target_lang}), numbered:\n{numbered_list(target_tokens)}\n\n"
        "For every source word, list the index/indexes of the translation "
        "word(s) it corresponds to, and vice versa. Only use the numbers "
        "shown above. A word's match should reflect actual meaning "
        "correspondence, not position -- do not default to a word's own "
        "index or a running count unless that genuinely is the correct "
        "correspondence at that point."
        #
        "For every source word, determine its translation in the other language (which may be one or more words, or nothing for a grammatical particle). "
        "Then, find the index or indexes of the specific instance of that lexeme in the opposite text. "
    )


def _alignment_few_shot_messages():
    messages = []
    for words_a, words_b, annot_a, annot_b, lang_a, lang_b in [
        (DAODEJING_SOURCE_WORDS, DAODEJING_TARGET_WORDS, DAODEJING_SOURCE_ANNOT, DAODEJING_TARGET_ANNOT, "zh", "en"),
        (SPANISH_JOKE_SOURCE_WORDS, SPANISH_JOKE_TARGET_WORDS, SPANISH_JOKE_SOURCE_ANNOT, SPANISH_JOKE_TARGET_ANNOT, "es", "en"),
    ]:
        messages.append({"role": "user", "content": build_alignment_prompt(words_a, words_b, lang_a, lang_b)})
        messages.append({"role": "assistant", "content": json.dumps({"source": annot_a, "translation": annot_b}, ensure_ascii=False, indent=2)})
    return messages


def align_and_annotate(model, source_text, target_text, source_lang, target_lang, context=""):
    source_tokens = tokenize(source_text, source_lang)
    target_tokens = tokenize(target_text, target_lang)
    schema = alignment_schema(source_lang, target_lang, len(source_tokens), len(target_tokens))

    messages = [
        {"role": "system", "content": "You are an expert translator and linguist doing word-level alignment."},
        *_alignment_few_shot_messages(),
        {"role": "user", "content": build_alignment_prompt(source_tokens, target_tokens, source_lang, target_lang, context)},
    ]
    response_format = {"type": "json_object", "schema": schema.model_json_schema()}
    result = model.create_chat_completion(messages=messages, response_format=response_format)
    parsed = json.loads(result["choices"][0]["message"]["content"])

    for i, tok in enumerate(source_tokens):
        parsed["source"][i]["word"] = tok
    for i, tok in enumerate(target_tokens):
        parsed["translation"][i]["word"] = tok
    return parsed


# =======================================================================
# 6. SENTENCE-GROUPING CALL -- replaces the naive regex-split + zip.
# =======================================================================
# Same principle as word alignment: show the model both fully-numbered
# lists up front, ask only for groupings. Because it's a grouping (not a
# positional zip), it handles merges, splits, reorders, and dropped/added
# sentences -- which is exactly the "creative translation" case a strict
# 1:1 zip can't survive.

def build_grouping_prompt(source_sents, target_sents, source_lang, target_lang):
    return (
        f"SOURCE ({source_lang}) sentences, numbered:\n{numbered_list(source_sents)}\n\n"
        f"TRANSLATION ({target_lang}) sentences, numbered:\n{numbered_list(target_sents)}\n\n"
        "Group these into corresponding units, in order. A group is usually "
        "one source sentence and one translation sentence, but translators "
        "often merge two source sentences into one translated sentence, "
        "split one into several, reorder them, or drop/add a sentence "
        "entirely -- represent those cases honestly rather than forcing a "
        "1:1 mapping. Every sentence on both sides must appear in exactly "
        "one group."
    )


def _grouping_few_shot_messages():
    messages = []
    for ex in GROUPING_EXAMPLES:
        messages.append({"role": "user", "content": build_grouping_prompt(ex["source_sents"], ex["target_sents"], ex["source_lang"], ex["target_lang"])})
        messages.append({"role": "assistant", "content": json.dumps({"groups": ex["groups"]})})
    return messages


def group_sentences(model, source_sents, target_sents, source_lang, target_lang):
    messages = [
        {"role": "system", "content": "You are an expert translator aligning sentences between a source text and its translation."},
        *_grouping_few_shot_messages(),
        {"role": "user", "content": build_grouping_prompt(source_sents, target_sents, source_lang, target_lang)},
    ]
    response_format = {"type": "json_object", "schema": SentenceGrouping.model_json_schema()}
    result = model.create_chat_completion(messages=messages, response_format=response_format)
    return json.loads(result["choices"][0]["message"]["content"])["groups"]


# =======================================================================
# 7. TOP-LEVEL ORCHESTRATION.
# =======================================================================
# Note on cost: few-shot examples are now attached to every alignment
# call AND every grouping call, and there are more, smaller calls than
# the original one-shot design. If your runtime supports prompt/KV-cache
# reuse (llama.cpp does, for an unchanged leading prefix), keep the
# system + few-shot messages byte-identical across calls within a run --
# that shared prefix then only gets processed once instead of once per
# chunk, which mostly cancels out the added call count.

def align_document(model, source_text, target_text, source_lang, target_lang, cjk_granularity="dictionary"):
    source_sents = segment_sentences(source_text, source_lang)
    target_sents = segment_sentences(target_text, target_lang)
    groups = group_sentences(model, source_sents, target_sents, source_lang, target_lang)

    combined_source, combined_translation = [], []
    src_offset = tgt_offset = 0

    for gi, group in enumerate(groups):
        src_idxs, tgt_idxs = group["source"], group["translation"]

        if not src_idxs or not tgt_idxs:
            # Pure insertion/deletion: nothing on the other side to align
            # to, so there's no alignment call to make.
            for i in src_idxs:
                for tok in tokenize(source_sents[i - 1], source_lang, cjk_granularity):
                    combined_source.append({"word": tok, "meaning": [], "match": [], "footnote": None})
                src_offset += len(tokenize(source_sents[i - 1], source_lang, cjk_granularity))
            for i in tgt_idxs:
                for tok in tokenize(target_sents[i - 1], target_lang, cjk_granularity):
                    combined_translation.append({"word": tok, "meaning": [], "match": [], "footnote": None})
                tgt_offset += len(tokenize(target_sents[i - 1], target_lang, cjk_granularity))
            continue

        src_text = " ".join(source_sents[i - 1] for i in src_idxs)
        tgt_text = " ".join(target_sents[i - 1] for i in tgt_idxs)

        # Neighboring group's raw text as inert context -- informs meaning
        # and footnotes without being indexable, so it can't reintroduce
        # the forward-reference problem.
        prev_group = groups[gi - 1] if gi > 0 else None
        next_group = groups[gi + 1] if gi + 1 < len(groups) else None
        context_bits = []
        if prev_group and prev_group["source"]:
            context_bits.append(source_sents[prev_group["source"][-1] - 1])
        if next_group and next_group["source"]:
            context_bits.append(source_sents[next_group["source"][0] - 1])
        context = " ".join(context_bits)

        piece = align_and_annotate(model, src_text, tgt_text, source_lang, target_lang, context=context)
        for w in piece["source"]:
            w["match"] = [m + tgt_offset for m in w["match"]]
        for w in piece["translation"]:
            w["match"] = [m + src_offset for m in w["match"]]
        combined_source.extend(piece["source"])
        combined_translation.extend(piece["translation"])
        src_offset += len(piece["source"])
        tgt_offset += len(piece["translation"])

    return {"source": combined_source, "translation": combined_translation}