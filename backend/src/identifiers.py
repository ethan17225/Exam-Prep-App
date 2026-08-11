from uuid import uuid4

# 12 hex chars = 48 bits. The previous 8 chars was 32 bits, which reaches a ~1.2%
# collision probability by 10k rows — and `history` gains a row per submission
# forever, so it gets there first. A PK collision surfaces as a 500 on submit,
# i.e. a student losing a completed attempt. There is no retry loop; the entropy
# is simply wide enough that one is not needed.
ID_LENGTH = 12


def new_id() -> str:
    """Primary key for every table with a client-visible id."""
    return uuid4().hex[:ID_LENGTH]
