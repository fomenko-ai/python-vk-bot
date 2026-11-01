"""Safe exceptions: messages never include credentials or server payloads."""


class VKError(Exception):
    """Base class for library errors."""


class NetworkError(VKError):
    """A request could not complete; a mutation may already have reached VK."""


class HTTPError(VKError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"VK HTTP request failed with status {status_code}")


class APIError(VKError):
    def __init__(self, code: int, method: str) -> None:
        self.code = code
        self.method = method
        super().__init__(f"VK API error {code} in {method}")


class RateLimitError(APIError):
    """VK error 6; no retry or numeric rate assumption is made."""


class InvalidResponseError(VKError):
    """Malformed JSON or an unexpected response shape."""


class UploadError(VKError):
    """The upload server rejected a file; its potentially sensitive reply is omitted."""


class InvalidUpdateError(VKError):
    """An event does not match the supported data boundary."""


class CallbackAuthenticationError(VKError):
    """The Callback group or secret did not match."""


class LifecycleError(VKError):
    """An operation is invalid in the current lifecycle state."""
