from enum import StrEnum


class AttemptMode(StrEnum):
    """An attempt is either graded or a study run.

    This is the third component of the `(user_id, exam_id, mode)` upsert key, so
    leaving it free-form let a client mint unlimited attempt rows — each carrying
    megabytes of JSONB — simply by varying the string.
    """

    EXAM = "exam"
    PRACTICE = "practice"


# Slack on the deadline for clock skew and a slow final autosave. Answers that
# arrive after the limit plus this grace are not graded.
SUBMIT_GRACE_SECONDS = 120
