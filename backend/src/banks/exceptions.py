from src.exceptions import DetailedHTTPException


class BankNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Question bank not found"


class SectionNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Section not found"


class BankInUse(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "This bank has exams linked to it. Delete those exams first."


class EmptySectionName(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Section name cannot be empty"


class EmptyBankTitle(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Title cannot be empty"


class DuplicateSectionShare(DetailedHTTPException):
    STATUS_CODE = 400
    DETAIL = "Each section can only appear once in the mix"


class EmptyBankDraw(DetailedHTTPException):
    STATUS_CODE = 409
    DETAIL = "Section percentages must draw at least one question from the bank"
