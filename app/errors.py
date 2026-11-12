"""Single error type; every failure leaves the API as {"error": {"code", "message", ...}}."""


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def body(self) -> dict:
        err = {"code": self.code, "message": self.message}
        err.update(self.extra)
        return {"error": err}


def validation(message: str) -> ApiError:
    return ApiError(422, "VALIDATION", message)


def not_found(message: str = "Not found") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)
