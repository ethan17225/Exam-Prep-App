"""Import manifest for every ORM model.

Alembic's `target_metadata` is only complete if every model module has been
imported; anything missing here is proposed as a DROP TABLE by autogenerate.
`src/main.py` imports this too, so a missing model fails at boot rather than on
the first request that touches the relationship.

`__all__` is load-bearing: without it a linter or editor strips these as unused
imports and autogenerate silently starts dropping tables.
"""

from src.attempts.models import History, InProgressExam
from src.auth.models import User
from src.courses.models import Course
from src.exams.models import Exam, Question

__all__ = ["Course", "Exam", "History", "InProgressExam", "Question", "User"]
