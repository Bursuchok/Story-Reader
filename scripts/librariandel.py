
    
  

import argparse
import json
import os
import re
import sys
import tempfile

from pathlib import Path
from urllib.parse import quote


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

INBOX = ROOT / "New Stories"
PUBLISHED = ROOT / "Published Stories"
SAVES = ROOT / "Saves"
CATALOG = ROOT / "catalog.json"

METADATA_MARKER = "<!-- STORY-METADATA -->"
CONTENT_MARKER = "<!-- STORY-CONTENT -->"

OPENING_TAG = "<<storytype>>"
CLOSING_TAG = "<</storytype>>"
SAVEHERE_PATTERN = re.compile(r"<<\s*savehere\s*>>")
PAUSE_PATTERN = re.compile(r"<<\s*pause\s+[\d.]+\s*>>")
MIN_SAVEHERE_COUNT = 3

RAW_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Bursuchok/Story-Reader/refs/heads/main/"
)

PUBLISHED_URL_PREFIX = (
    RAW_BASE_URL + quote("Published Stories", safe="/") + "/"
)

# Обов'язкові поля нової історії.
REQUIRED_FIELDS = [
    "title",
    "author",
    "genres",
    "description",
    "detailedDescription",
    "theme",
    "ageRating",
]

# Необов'язкові поля.
OPTIONAL_FIELDS = [
    "readingTime",
    "contentWarnings",
    "ratingDescription",
]

# Межі довжини не блокують публікацію.
FIELD_LENGTH_LIMITS = {
    "title": 100,
    "description": 300,
    "detailedDescription": 1500,
    "ratingDescription": 1000,
}


# ============================================================
# ПОМИЛКИ ТА СТАТИСТИКА
# ============================================================

class PublishError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def error(code, message):
    raise PublishError(code, message)


stats = {
    "added": 0,
    "updated": 0,
    "unchanged": 0,
    "removed": 0,
    "orphans": 0,
    "saved": 0,
    "warnings": 0,
}


def warning(message):
    stats["warnings"] += 1

