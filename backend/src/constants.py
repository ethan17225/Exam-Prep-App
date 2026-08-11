# Wire-format bounds shared by more than one domain's schemas. Keeping them here
# stops `attempts.schemas` from importing `exams.schemas` for a number.

# Postgres INTEGER is 32-bit; an out-of-range value is a driver error (500) that,
# on submit, costs the student their completed attempt. Bound it to a 422 instead.
MAX_INT = 2_147_483_647

MAX_QUESTIONS_PER_EXAM = 1000
