"""The ten bounded contexts of the hub."""

from enum import StrEnum


class Context(StrEnum):
    DIRECTION = "direction"
    ACQUISITION = "acquisition"
    PREPARATION = "preparation"
    DETECTION = "detection"
    MODELING = "modeling"
    CATALOG = "catalog"
    VETTING = "vetting"
    REVIEW = "review"
    FOLLOWUP = "followup"
    REPORTING = "reporting"
