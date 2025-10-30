"""Tests for input validation utilities."""

import pytest
from utils.validators import Validator, ValidationResult


class TestBoardNameValidator:
    def test_valid_board_name(self):
        result = Validator.board_name("My Board")
        assert result.ok is True
        assert result.message is None
    
    def test_empty_board_name(self):
        result = Validator.board_name("")
        assert result.ok is False
        assert "empty" in result.message.lower()
    
    def test_too_long_board_name(self):
        long_name = "A" * (Validator.BOARD_NAME_LIMIT + 1)
        result = Validator.board_name(long_name)
        assert result.ok is False
        assert str(Validator.BOARD_NAME_LIMIT) in result.message


class TestColumnNameValidator:
    def test_valid_column_name(self):
        result = Validator.column_name("In Progress")
        assert result.ok is True
    
    def test_empty_column_name(self):
        result = Validator.column_name("")
        assert result.ok is False


class TestTaskTitleValidator:
    def test_valid_task_title(self):
        result = Validator.task_title("Complete feature implementation")
        assert result.ok is True
    
    def test_empty_task_title(self):
        result = Validator.task_title("")
        assert result.ok is False


class TestSearchQueryValidator:
    def test_valid_search_query(self):
        result = Validator.search_query("task")
        assert result.ok is True
    
    def test_too_short_search_query(self):
        result = Validator.search_query("ab")
        assert result.ok is False
        assert "3 characters" in result.message
    
    def test_too_long_search_query(self):
        long_query = "A" * 81
        result = Validator.search_query(long_query)
        assert result.ok is False


class TestReminderTimeValidator:
    def test_valid_reminder_time(self):
        result = Validator.reminder_time("09:00")
        assert result.ok is True
    
    def test_invalid_reminder_time_format(self):
        result = Validator.reminder_time("9:00")
        assert result.ok is False
    
    def test_invalid_reminder_time_hours(self):
        result = Validator.reminder_time("25:00")
        assert result.ok is False


class TestDueDateParser:
    def test_parse_today(self):
        from datetime import datetime, timezone
        result = Validator.parse_due_date("today")
        assert result is not None
        # Should be today at 23:59:59 UTC
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.hour == 23
        assert parsed.minute == 59
    
    def test_parse_tomorrow(self):
        result = Validator.parse_due_date("tomorrow")
        assert result is not None
    
    def test_parse_iso_date(self):
        result = Validator.parse_due_date("2025-12-31T23:59:59Z")
        assert result is not None
    
    def test_parse_invalid_date(self):
        with pytest.raises(ValueError):
            Validator.parse_due_date("invalid-date")

