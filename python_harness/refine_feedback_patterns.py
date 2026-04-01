import re

MYPY_LINE_PATTERN = re.compile(
    r"^(?P<file>[^:\n]+\.py):(?P<line>\d+): (?P<kind>error|note): (?P<message>.+)$"
)
RUFF_HEADER_PATTERN = re.compile(r"^(?P<code>[A-Z]{1,4}\d+)\b(?P<message>.*)$")
RUFF_LOCATION_PATTERN = re.compile(
    r"^--> (?P<file>[^:\n]+\.py):(?P<line>\d+):\d+"
)
PYTEST_FAILED_PATTERN = re.compile(
    r"^FAILED (?P<file>[^:\s]+\.py)(?:::.*)? - (?P<message>.+)$"
)
