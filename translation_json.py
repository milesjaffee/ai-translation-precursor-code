from typing import List
from pydantic import BaseModel, Field

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
    """Model for a full annotated aligned translation"""
    source: AnnotatedTranslationSide = Field(..., description="The source side of an annotated translation.")
    translation: AnnotatedTranslationSide = Field(..., description="The post-translation side of an annotated translation.")