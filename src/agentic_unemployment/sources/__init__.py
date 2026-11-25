from __future__ import annotations

from agentic_unemployment.sources import jobinja, jobvision

SOURCES = {
    "jobinja": jobinja,
    "jobvision": jobvision,
}
SOURCE_NAMES = tuple(SOURCES)
