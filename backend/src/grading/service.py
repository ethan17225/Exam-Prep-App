"""The single source of truth for correctness across every question type.

Three consumers in three domains: `attempts` (submit), `admin` (dashboard), and
`exams` (type counts). That is why this is a leaf package importing nothing from
the rest of the app — anywhere else and the import graph cycles.

`grade_question` and `question_type_counts` must stay in this file together:
the latter classifies questions using the same rules, and separating them makes
drift between the two invisible.

Adding a question type means touching three things at once:
`constants.QuestionType`, `constants.ADVANCED_TYPES`, and `grade_question`.
"""

from typing import Any, NamedTuple

from src.grading.constants import ADVANCED_TYPES, FIB_TYPES, QuestionType
from src.grading.utils import grouped_answer_map, norm_str_list, norm_str_set


class TypeCountRow(NamedTuple):
    """Just enough of a question for `question_type_counts`, so listing exams
    never loads the JSONB payloads."""

    type: str | None
    options: Any


class GradableRow(NamedTuple):
    """Just enough of a question for `grade_question`, so the admin dashboard
    never loads question text, rationale or sections."""

    type: str | None
    answer: Any
    options: Any


def _normalized_type(q) -> str:
    return (q.type or "").strip().upper()


def is_fib_question(q) -> bool:
    qtype = _normalized_type(q)
    if qtype in ADVANCED_TYPES:
        return False
    return qtype in FIB_TYPES or not q.options


def question_type_counts(questions: list) -> tuple[int, int, int, int]:
    """Return (mcq, sata, fib, other) using the same rules as submit grading."""
    mcq = sata = fib = other = 0
    for q in questions:
        qtype = _normalized_type(q)
        if qtype in ADVANCED_TYPES:
            other += 1
        elif qtype == QuestionType.SATA:
            sata += 1
        # Calls the shared predicate rather than restating its rule, which is the
        # whole reason these two functions live in one file.
        elif is_fib_question(q):
            fib += 1
        else:
            mcq += 1
    return mcq, sata, fib, other


def grade_question(q, user_answer, *, fuzzy_fib: bool = True) -> bool:
    """Shared grading logic for all question types (except FIB self-marking).

    `fuzzy_fib=False` disables the lenient substring match on free-text answers.
    Graded attempts pass False: self-marking is practice-only, so without this
    the leniency documented below would decide real marks.
    """
    expected = q.answer
    qtype = _normalized_type(q)

    if qtype in (QuestionType.MATRIX, QuestionType.BOWTIE):
        return grouped_answer_map(user_answer) == grouped_answer_map(expected)

    if qtype == QuestionType.CLOZE:
        user_list = norm_str_list(user_answer if isinstance(user_answer, list) else None)
        expected_list = norm_str_list(expected)
        # The length check short-circuits, so zip never sees unequal lengths.
        return len(user_list) == len(expected_list) and all(
            u.lower() == e.lower() for u, e in zip(user_list, expected_list, strict=True)
        )

    if qtype == QuestionType.RANKING:
        user_list = norm_str_list(user_answer if isinstance(user_answer, list) else None)
        expected_list = norm_str_list(expected)
        return len(user_list) == len(expected_list) and user_list == expected_list

    if qtype == QuestionType.HIGHLIGHT:
        return norm_str_set(user_answer) == norm_str_set(expected)

    if qtype == QuestionType.HOTSPOT:
        return bool(user_answer) and str(user_answer).strip() == str(expected).strip()

    if qtype == QuestionType.SATA:
        return norm_str_set(expected) == norm_str_set(user_answer)

    if is_fib_question(q):
        user_str = str(user_answer or "").strip().lower()
        expected_str = str(expected).strip().lower()
        try:
            return float(user_str) == float(expected_str)
        except (ValueError, TypeError):
            if not fuzzy_fib:
                return user_str == expected_str
            # Deliberately lenient on free text: a 3+ character substring match
            # counts either way, so "tach" is accepted for "tachycardia". Typing
            # a short common word can therefore score a mark it did not earn —
            # the trade is that FIB answers are otherwise unmarkable, and the UI
            # offers self-marking (`fib_correct`) for the cases this gets wrong.
            return (
                user_str == expected_str
                or (len(user_str) >= 3 and user_str in expected_str)
                or (len(expected_str) >= 3 and expected_str in user_str)
            )

    return str(user_answer or "").strip() == str(expected).strip()
