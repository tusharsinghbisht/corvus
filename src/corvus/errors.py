"""Errors that callers can distinguish from a successful empty search."""


class ConfigError(ValueError):
    pass


class BackendError(RuntimeError):
    def __init__(self, code: str, message: str, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status

    def as_dict(self):
        return {"code": self.code, "message": str(self), "http_status": self.status}
