"""Tool errors and their exit codes (spec: 2 invalid input, 3 data not available)."""


class ToolError(Exception):
    exit_code = 1


class InvalidInputError(ToolError):
    exit_code = 2


class DataNotAvailableError(ToolError):
    exit_code = 3


class ServiceUnavailableError(ToolError):
    """A remote service failed or did not answer in time: transient, rerun the tool. Not
    the same as data that does not exist (DataNotAvailableError, exit 3)."""

    exit_code = 1
