from enum import StrEnum


class QuestionType(StrEnum):
    """Known question types.

    Note that `QuestionIn.type` is a plain `str`, not this enum: the documented
    JSON upload format allows arbitrary type strings (e.g. "FILL-IN-THE-BLANK")
    and grading normalizes them. This exists for comparisons, not validation.
    """

    MCQ = "MCQ"
    SATA = "SATA"
    FIB = "FIB"
    MATRIX = "MATRIX"
    CLOZE = "CLOZE"
    BOWTIE = "BOWTIE"
    RANKING = "RANKING"
    HIGHLIGHT = "HIGHLIGHT"
    HOTSPOT = "HOTSPOT"


# Next-Gen NCLEX style types with structured options/answers.
ADVANCED_TYPES = {
    QuestionType.MATRIX,
    QuestionType.CLOZE,
    QuestionType.BOWTIE,
    QuestionType.RANKING,
    QuestionType.HIGHLIGHT,
    QuestionType.HOTSPOT,
}

FIB_TYPES = {QuestionType.FIB, "FILL-IN-THE-BLANK"}

# Mirrored by the frontend's overview chart line (overview.ts) and the README.
# Deliberately not an env var — all three must change together or none.
PASS_THRESHOLD = 0.72
