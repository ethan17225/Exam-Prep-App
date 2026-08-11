from src.exceptions import DetailedHTTPException


class DocumentNotFound(DetailedHTTPException):
    STATUS_CODE = 404
    DETAIL = "Document not found"
