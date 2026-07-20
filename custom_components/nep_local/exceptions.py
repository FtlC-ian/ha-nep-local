"""Exceptions raised by the NEP local protocol client."""


class NepError(Exception):
    """Base NEP protocol error."""


class NepConnectionError(NepError):
    """The gateway could not be reached."""


class NepInvalidResponse(NepError):
    """The gateway returned a response that could not be parsed."""


class NepResponseMissing(NepError):
    """The requested response was absent."""
