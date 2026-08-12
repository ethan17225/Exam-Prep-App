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

# The passing score, as a percentage, for an exam whose creator did not choose
# one. Every exam carries its own `pass_grade` and every graded attempt copies the
# threshold it was scored against onto its History row, so this is only ever a
# default for new exams — never the value a comparison is made against.
DEFAULT_PASS_GRADE = 72
