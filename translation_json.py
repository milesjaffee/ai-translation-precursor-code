from typing import List
from pydantic import BaseModel, Field

class WordInAnnotatedTranslation(BaseModel):
    """Model for one word in an annotated aligned translation."""
    word: str = Field(..., description="")
    meaning: List[str] = Field
    match: List[int]

    latin: str | None = Field(default=None)
    footnote: str | None =Field(default=None)


class AnnotatedTranslationPart(BaseModel):
    """Model for either the source or the translation half of an annotated aligned translation."""
    lang: str = Field(..., description="Language of this part")
    text: dict[int, WordInAnnotatedTranslation] = Field({}, description="")

class AnnotatedTranslation(BaseModel):
    """Model for a full annotated aligned translation"""
    source: AnnotatedTranslationPart = Field(..., description="")
    translation: AnnotatedTranslationPart = Field(..., description="")