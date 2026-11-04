class ServiceError(Exception):
    def __init__(self, code: str, message: str, status: int, sdk_code: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.sdk_code = sdk_code
