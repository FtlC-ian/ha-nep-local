"""Protocol exceptions which retain the distinction between no data and zero."""


class NepError(Exception):
    """Base error for local NEP gateway communication."""


class NepResponseMissing(NepError):
    """The gateway returned no resource (for example HTTP 404/204)."""


class NepInvalidResponse(NepError):
    """The gateway replied, but its payload was not usable for this endpoint."""
