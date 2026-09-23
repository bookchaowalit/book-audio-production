"""Stable, sanitized errors exposed by the audio product."""


class AudioError(ValueError):
    """A user-actionable failure with a stable code and safe public message."""

    def __init__(self, code: str, public_message: str, retryable: bool = False) -> None:
        super().__init__(public_message)
        self.code = code
        self.retryable = retryable
