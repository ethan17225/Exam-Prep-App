import pathlib
import re
import urllib.parse

from src.documents.constants import DOCS_URL_PREFIX

_BODY_RE = re.compile(r"<body[^>]*>(.*)</body>", re.DOTALL)


def safe_resolve(root: pathlib.Path, path_param: str) -> pathlib.Path | None:
    """Resolve a client-supplied document path inside `root`, or None.

    Containment is checked after `.resolve()` so that "../" — including its
    percent-encoded forms — cannot escape the documents directory.
    """
    decoded = urllib.parse.unquote(path_param)
    rel = decoded.removeprefix(f"{DOCS_URL_PREFIX}/").removeprefix("/")
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root.resolve()):
        return None
    return candidate


def read_body_html(path: pathlib.Path) -> str:
    """Read a document and strip everything outside <body>.

    Blocking read plus a DOTALL regex over the whole file, kept together so the
    caller offloads it in one threadpool hop.
    """
    content = path.read_text(encoding="utf-8")
    match = _BODY_RE.search(content)
    return match.group(1).strip() if match else content
