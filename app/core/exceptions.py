class AppException(RuntimeError):
    def __init__(self, code=5000, message="处理失败", status_code=500):
        super().__init__(message)
