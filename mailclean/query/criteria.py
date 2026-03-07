"""Criterion classes for query matching."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from ..utils import (
    parse_date,
    parse_relative_date,
    parse_regex_pattern,
    normalize_email,
    wildcard_to_regex,
)


if TYPE_CHECKING:
    from ..models import EmailMessage


class Criterion(ABC):
    """Base class for all query criteria."""

    @abstractmethod
    def matches(self, email: 'EmailMessage') -> bool:
        """Check if the email matches this criterion."""
        pass

    @property
    def requires_body(self) -> bool:
        """Return True if this criterion needs email body content."""
        return False

    @property
    def requires_headers(self) -> bool:
        """Return True if this criterion needs the full headers dict (arbitrary headers)."""
        return False

    @abstractmethod
    def __repr__(self) -> str:
        pass


class FromCriterion(Criterion):
    """Match emails by sender address."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex = re.compile(wildcard_to_regex(pattern), re.IGNORECASE)

    def matches(self, email: 'EmailMessage') -> bool:
        return bool(self.regex.search(email.from_address))

    def __repr__(self) -> str:
        return f"From({self.pattern!r})"


class ToCriterion(Criterion):
    """Match emails by To recipient."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex = re.compile(wildcard_to_regex(pattern), re.IGNORECASE)

    def matches(self, email: 'EmailMessage') -> bool:
        return any(self.regex.search(addr) for addr in email.to_addresses)

    def __repr__(self) -> str:
        return f"To({self.pattern!r})"


class CcCriterion(Criterion):
    """Match emails by CC recipient."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex = re.compile(wildcard_to_regex(pattern), re.IGNORECASE)

    def matches(self, email: 'EmailMessage') -> bool:
        return any(self.regex.search(addr) for addr in email.cc_addresses)

    def __repr__(self) -> str:
        return f"Cc({self.pattern!r})"


class BccCriterion(Criterion):
    """Match emails by BCC recipient."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex = re.compile(wildcard_to_regex(pattern), re.IGNORECASE)

    def matches(self, email: 'EmailMessage') -> bool:
        return any(self.regex.search(addr) for addr in email.bcc_addresses)

    def __repr__(self) -> str:
        return f"Bcc({self.pattern!r})"


class AddresseeCriterion(Criterion):
    """Match emails by any recipient (To, CC, or BCC)."""

    def __init__(self, pattern: str):
        self.pattern = pattern
        self.regex = re.compile(wildcard_to_regex(pattern), re.IGNORECASE)

    def matches(self, email: 'EmailMessage') -> bool:
        return any(self.regex.search(addr) for addr in email.all_recipients)

    def __repr__(self) -> str:
        return f"Addressee({self.pattern!r})"


class DateCriterion(Criterion):
    """Match emails by exact date."""

    def __init__(self, date_str: str):
        self.date_str = date_str
        self.target_date = parse_date(date_str)
        if self.target_date is None:
            raise ValueError(f"Invalid date: {date_str}")

    def matches(self, email: 'EmailMessage') -> bool:
        if email.date is None:
            return False
        return email.date.date() == self.target_date.date()

    def __repr__(self) -> str:
        return f"Date({self.date_str!r})"


class BeforeCriterion(Criterion):
    """Match emails before a specific date."""

    def __init__(self, date_str: str):
        self.date_str = date_str
        self.target_date = parse_date(date_str)
        if self.target_date is None:
            raise ValueError(f"Invalid date: {date_str}")

    def matches(self, email: 'EmailMessage') -> bool:
        if email.date is None:
            return False
        return email.date < self.target_date

    def __repr__(self) -> str:
        return f"Before({self.date_str!r})"


class AfterCriterion(Criterion):
    """Match emails after a specific date."""

    def __init__(self, date_str: str):
        self.date_str = date_str
        self.target_date = parse_date(date_str)
        if self.target_date is None:
            raise ValueError(f"Invalid date: {date_str}")

    def matches(self, email: 'EmailMessage') -> bool:
        if email.date is None:
            return False
        return email.date > self.target_date

    def __repr__(self) -> str:
        return f"After({self.date_str!r})"


class OlderThanCriterion(Criterion):
    """Match emails older than a relative time period."""

    def __init__(self, relative_str: str):
        self.relative_str = relative_str
        # Store the original string, compute cutoff at match time
        self._validate(relative_str)

    def _validate(self, relative_str: str) -> None:
        if parse_relative_date(relative_str) is None:
            raise ValueError(f"Invalid relative date: {relative_str}")

    def _get_cutoff(self) -> datetime:
        return parse_relative_date(self.relative_str)

    def matches(self, email: 'EmailMessage') -> bool:
        if email.date is None:
            return False
        cutoff = self._get_cutoff()
        return email.date < cutoff

    def __repr__(self) -> str:
        return f"OlderThan({self.relative_str!r})"


class NewerThanCriterion(Criterion):
    """Match emails newer than a relative time period."""

    def __init__(self, relative_str: str):
        self.relative_str = relative_str
        self._validate(relative_str)

    def _validate(self, relative_str: str) -> None:
        if parse_relative_date(relative_str) is None:
            raise ValueError(f"Invalid relative date: {relative_str}")

    def _get_cutoff(self) -> datetime:
        return parse_relative_date(self.relative_str)

    def matches(self, email: 'EmailMessage') -> bool:
        if email.date is None:
            return False
        cutoff = self._get_cutoff()
        return email.date > cutoff

    def __repr__(self) -> str:
        return f"NewerThan({self.relative_str!r})"


class SubjectCriterion(Criterion):
    """Match emails by subject using regex."""

    def __init__(self, pattern_str: str):
        self.pattern_str = pattern_str
        pattern, flags = parse_regex_pattern(pattern_str)
        self.regex = re.compile(pattern, flags)

    def matches(self, email: 'EmailMessage') -> bool:
        return bool(self.regex.search(email.subject))

    def __repr__(self) -> str:
        return f"Subject({self.pattern_str!r})"


class BodyCriterion(Criterion):
    """Match emails by body content using regex."""

    def __init__(self, pattern_str: str):
        self.pattern_str = pattern_str
        pattern, flags = parse_regex_pattern(pattern_str)
        self.regex = re.compile(pattern, flags)

    def matches(self, email: 'EmailMessage') -> bool:
        if email.body is None:
            return False
        return bool(self.regex.search(email.body))

    @property
    def requires_body(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"Body({self.pattern_str!r})"


class HeaderCriterion(Criterion):
    """Match emails by any arbitrary header field."""

    def __init__(self, header_name: str, pattern_str: str):
        self.header_name = header_name.lower()
        self.pattern_str = pattern_str
        if pattern_str.startswith('/'):
            pattern, flags = parse_regex_pattern(pattern_str)
        else:
            pattern = wildcard_to_regex(pattern_str)
            flags = 0
        self.regex = re.compile(pattern, flags)

    def matches(self, email: 'EmailMessage') -> bool:
        for key, value in email.headers.items():
            if key.lower() == self.header_name:
                return bool(self.regex.search(value))
        return False

    @property
    def requires_headers(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"Header({self.header_name!r}, {self.pattern_str!r})"


class AndCriterion(Criterion):
    """Combine criteria with AND logic."""

    def __init__(self, left: Criterion, right: Criterion):
        self.left = left
        self.right = right

    def matches(self, email: 'EmailMessage') -> bool:
        return self.left.matches(email) and self.right.matches(email)

    @property
    def requires_body(self) -> bool:
        return self.left.requires_body or self.right.requires_body

    @property
    def requires_headers(self) -> bool:
        return self.left.requires_headers or self.right.requires_headers

    def __repr__(self) -> str:
        return f"And({self.left!r}, {self.right!r})"


class OrCriterion(Criterion):
    """Combine criteria with OR logic."""

    def __init__(self, left: Criterion, right: Criterion):
        self.left = left
        self.right = right

    def matches(self, email: 'EmailMessage') -> bool:
        return self.left.matches(email) or self.right.matches(email)

    @property
    def requires_body(self) -> bool:
        return self.left.requires_body or self.right.requires_body

    @property
    def requires_headers(self) -> bool:
        return self.left.requires_headers or self.right.requires_headers

    def __repr__(self) -> str:
        return f"Or({self.left!r}, {self.right!r})"


class NotCriterion(Criterion):
    """Negate a criterion."""

    def __init__(self, criterion: Criterion):
        self.criterion = criterion

    def matches(self, email: 'EmailMessage') -> bool:
        return not self.criterion.matches(email)

    @property
    def requires_body(self) -> bool:
        return self.criterion.requires_body

    @property
    def requires_headers(self) -> bool:
        return self.criterion.requires_headers

    def __repr__(self) -> str:
        return f"Not({self.criterion!r})"
