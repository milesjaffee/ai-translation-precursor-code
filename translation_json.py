import time
import json
from typing import List
from pydantic import BaseModel, Field
from llama_cpp import Llama

class WordInAnnotatedTranslation(BaseModel):
    """Model for one word in an annotated aligned translation."""
    word: str = Field(..., description="The word in the language of this side of the translation.")
    meaning: List[str] = Field(..., description="Possible meanings of the word in the language of the other side of the translation. Doesn't have to match up.")
    match: List[int] = Field(..., description="A list of the indexes of the words on the other side of the translation that correspond to this word on this side. This list can be empty (for a grammatical particle or phrasing that isn't used in the other language), have one element (a simple case of a word that just translates directly into another word), or contain multiple, possibly non-contiguous indexes (for the introduction of grammatical particles or the expansion of terms that only work in one language). In any case, these indexes correspond to the integer index numbers in the word list of the other side of the translation. This field should be one of the last items to be filled in, as the translation should be complete and all words should be in place before the indexes are matched up.")

    latin: str | None = Field(default=None, description="The Latin-alphabet transcription of any non-Latin characters present, such as pinyin for Chinese characters. This is not used on the json if this side of the translation uses a language with the Latin alphabet.")
    footnote: str | None =Field(default=None, description="An optional note explaining a word, phrase, joke/pun, or idiom that doesn't translate directly or is highly ambiguous. Only present in cases of confusion, substantial rephrasing, or jokes/idioms.")


class AnnotatedTranslationSide(BaseModel):
    """Model for either the source or the translation side of an annotated aligned translation."""
    lang: str = Field(..., description="Language of this side of the translation.")
    text: dict[int, WordInAnnotatedTranslation] = Field({}, description="List of words on this side of the translation, ordered by an integer index. You should create the translations first, then put them in this list format, then finally set the 'match' fields per word.")

class AnnotatedTranslation(BaseModel):
    """Model for an annotated aligned translation"""
    source: AnnotatedTranslationSide = Field(..., description="The source side of an annotated translation.")
    translation: AnnotatedTranslationSide = Field(..., description="The post-translation side of an annotated translation.")

class AnnotatedTranslationRequest(BaseModel):
    """Model for a request to the AI to produce an annotated aligned translation."""
    source: str = Field(..., description="The source text to be translated.")
    source_lang: str = Field(..., description="The language of the source text.")
    target_lang: str = Field(..., description="The language to translate the source text into.")

#Example
daodejing1 = AnnotatedTranslation(
    source=AnnotatedTranslationSide(
        lang="zh",
        text={
            1: WordInAnnotatedTranslation(
                word= "道",
				meaning=["The Tao", "way", "path", "to speak", "to guide"],
				match=[1,2],
				latin= "dào",
            ),
            2: WordInAnnotatedTranslation(
                word= "可",
                meaning=["can", "may", "able to"],
                match=[3,4],
                latin= "kě",
            ),
            3: WordInAnnotatedTranslation(
                word= "道,",
                meaning=["The Tao", "way", "path", "to speak", "to guide"],
                match=[5,6,7],
                latin= "dào",
            ),
            4: WordInAnnotatedTranslation(
                word= "非",
                meaning=["not", "non-", "un-"],
                match=[8,9],
                latin= "fēi",
            ),
            5: WordInAnnotatedTranslation(
                word= "常",
                meaning=["eternal", "constant", "unchanging"],
                match=[10,11],
                latin= "cháng",
            ),
            6: WordInAnnotatedTranslation(
                word= "道",
                meaning=["The Tao", "way", "path", "to speak", "to guide"],
                match=[12],
                latin= "dào",
            ),
        }
    ),
    translation=AnnotatedTranslationSide(
        lang="en",
        text={
            1: WordInAnnotatedTranslation(
                word="The",
                meaning=[],
                match=[],
            ),
            2: WordInAnnotatedTranslation(
                word="Way",
                meaning=["道"],
                match=[1],
            ),
            3: WordInAnnotatedTranslation(
                word="that",
                meaning=[],

                match=[],
            ),
            4: WordInAnnotatedTranslation(
                word="can",
                meaning= ["可", "能"],
                match=[2],
            ),
            5: WordInAnnotatedTranslation(
                word="be",
                meaning=[],

                match=[],
            ),
            6: WordInAnnotatedTranslation(
                word="spoken",
                meaning=["言"],
                match=[3],
                footnote="Note that the same character is used for both 'way' and 'to speak', making the direct translation ambiguous."
            ),
            7: WordInAnnotatedTranslation(
                word="of",
                meaning=[],
                match=[],
            ),
            8: WordInAnnotatedTranslation(
                word="is",
                meaning=[],
                match=[],
            ),
            9: WordInAnnotatedTranslation(
                word="not",
                meaning=["不"],
                match=[4],
            ),
            10: WordInAnnotatedTranslation(
                word="the",
                meaning=[],
                match=[],
            ),
            11: WordInAnnotatedTranslation(
                word="eternal",
                meaning=["常"],
                match=[5],
            ),
            12: WordInAnnotatedTranslation(
                word="Way",
                meaning=["道"],
                match=[6],
            ),
        }
    )
)
#print(daodejing1.model_json_schema())

request_daodejing1 = AnnotatedTranslationRequest(
    source="""道可道，非常道""",
    source_lang="zh",
    target_lang="en"
)

request_spanish_joke = AnnotatedTranslationRequest(
    source="""¡Socorro, me ha picado una víbora!
    ¿Cobra?
    No, gratis.""",
    source_lang="es",
    target_lang="en"
)

#===================AI stuff begins here

checkpoint = "LiquidAI/LFM2.5-2.6B-GGUF"
model = Llama.from_pretrained(checkpoint, device_map="auto", load_in_8bit=True, trust_remote_code=True, filename="*Q8_0.gguf", n_ctx=8192, n_batch=512, n_gpu_layers=32, verbose=True)

messages = [
    {
        "role": "system",
        "content": "You are an expert translator and linguist. Given a source text in one language, you will provide an annotated aligned translation, where each word in the source text is matched with its corresponding word(s) in your translated text. The output should be in JSON format, following the structure of the AnnotatedTranslation model."
        f"Follow this schema: {json.dumps(AnnotatedTranslation.model_json_schema(), indent=2)}",
    },
    {"role": "user", "content": f"{request_daodejing1.model_dump_json(indent=2)}"},
    {"role": "assistant", "content": f"{daodejing1.model_dump_json(indent=2)}"},
    {"role": "user", "content": f"{request_spanish_joke.model_dump_json(indent=2)}"},
]
response_format = {"type": "json_object", "schema": AnnotatedTranslation.model_json_schema()}

start = time.time()

outputs = model.create_chat_completion(
    messages=messages, response_format=response_format
)

print(outputs["choices"][0]["message"]["content"])

print(f"Time: {time.time() - start}")