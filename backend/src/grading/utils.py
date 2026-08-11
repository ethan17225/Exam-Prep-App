"""Answer normalizers.

Answers arrive from the client as a scalar, a list, or a comma-separated string
depending on the question type and how the exam JSON was authored. Every
comparison in `service.py` goes through one of these rather than inlining
`str().strip()` chains.
"""


def norm_str_set(values) -> set[str]:
    """Unordered comparison — SATA, HIGHLIGHT."""
    if values is None:
        return set()
    if isinstance(values, (list, tuple, set)):
        return {str(v).strip() for v in values if str(v).strip()}
    s = str(values).strip()
    return {p.strip() for p in s.split(",") if p.strip()} if s else set()


def norm_str_list(values) -> list[str]:
    """Ordered comparison — CLOZE, RANKING."""
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        return [str(v).strip() for v in values]
    return [str(values).strip()]


def grouped_answer_map(value) -> dict[str, set[str]]:
    """MATRIX/BOWTIE answers: key -> set of selections."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, set[str]] = {}
    for k, v in value.items():
        selections = norm_str_set(v)
        if selections:
            out[str(k).strip()] = selections
    return out
