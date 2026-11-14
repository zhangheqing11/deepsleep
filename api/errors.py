"""可直接呈现给前端的 API 错误，不包含底层异常内容。"""


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
