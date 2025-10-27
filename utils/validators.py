from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser

ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class ValidationResult:
    ok: bool
    message: Optional[str] = None


class Validator:
    BOARD_NAME_LIMIT = 80
    TASK_TITLE_LIMIT = 120
    COLUMN_NAME_LIMIT = 40

    @staticmethod
    def board_name(name: str) -> ValidationResult:
        if not name or not name.strip():
            return ValidationResult(False, "Board name cannot be empty.")
        if len(name.strip()) > Validator.BOARD_NAME_LIMIT:
            return ValidationResult(False, f"Board name must be under {Validator.BOARD_NAME_LIMIT} characters.")
        return ValidationResult(True)

    @staticmethod
    def column_name(name: str) -> ValidationResult:
        if not name or not name.strip():
            return ValidationResult(False, "Column name cannot be empty.")
        if len(name.strip()) > Validator.COLUMN_NAME_LIMIT:
            return ValidationResult(False, f"Column name must be under {Validator.COLUMN_NAME_LIMIT} characters.")
        return ValidationResult(True)

    @staticmethod
    def task_title(title: str) -> ValidationResult:
        if not title or not title.strip():
            return ValidationResult(False, "Task title cannot be empty.")
        if len(title.strip()) > Validator.TASK_TITLE_LIMIT:
            return ValidationResult(False, f"Task title must be under {Validator.TASK_TITLE_LIMIT} characters.")
        return ValidationResult(True)

    @staticmethod
    def parse_due_date(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        dt = parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        if dt < datetime.now(timezone.utc):
            raise ValueError("Due date must be in the future.")
        return dt.strftime(ISO_FORMAT)

    @staticmethod
    def search_query(term: str) -> ValidationResult:
        if len(term) < 3:
            return ValidationResult(False, "Search term must be at least 3 characters.")
        if len(term) > 80:
            return ValidationResult(False, "Search term too long (max 80).")
        return ValidationResult(True)

    @staticmethod
    def reminder_time(value: str) -> ValidationResult:
        if not re.match(r"^(?:[01]?\d|2[0-3]):[0-5]\d$", value):
            return ValidationResult(False, "Reminder time must be HH:MM in 24h format.")
        return ValidationResult(True)

    @staticmethod
    def sanitize(text: Optional[str]) -> Optional[str]:
        return text.strip() if text else text
