"""Utility functions for date parsing and helpers."""

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from dateutil import parser as date_parser


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse a date string into a datetime object."""
    try:
        return date_parser.parse(date_str)
    except (ValueError, TypeError):
        return None


def parse_relative_date(relative_str: str) -> Optional[datetime]:
    """
    Parse a relative date string like '30d', '2w', '3m' into a datetime.

    Returns the datetime that many units ago from now.
    """
    match = re.match(r'^(\d+)([dwm])$', relative_str.lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)

    now = datetime.now(timezone.utc)

    if unit == 'd':
        return now - timedelta(days=amount)
    elif unit == 'w':
        return now - timedelta(weeks=amount)
    elif unit == 'm':
        # Approximate months as 30 days
        return now - timedelta(days=amount * 30)

    return None


def parse_regex_pattern(pattern_str: str) -> tuple[str, int]:
    """
    Parse a regex pattern in /pattern/flags format.

    Returns (pattern, flags) tuple.
    """
    if not pattern_str.startswith('/'):
        return pattern_str, 0

    # Find the closing slash
    last_slash = pattern_str.rfind('/')
    if last_slash <= 0:
        return pattern_str, 0

    pattern = pattern_str[1:last_slash]
    flags_str = pattern_str[last_slash + 1:]

    flags = 0
    if 'i' in flags_str:
        flags |= re.IGNORECASE
    if 'm' in flags_str:
        flags |= re.MULTILINE
    if 's' in flags_str:
        flags |= re.DOTALL

    return pattern, flags


def format_date(dt: datetime) -> str:
    """Format a datetime for display."""
    return dt.strftime('%Y-%m-%d %H:%M')


def truncate_string(s: str, max_length: int = 50) -> str:
    """Truncate a string and add ellipsis if needed."""
    if len(s) <= max_length:
        return s
    return s[:max_length - 3] + '...'


def normalize_email(email: str) -> str:
    """Normalize an email address for comparison."""
    return email.lower().strip()


def wildcard_to_regex(pattern: str) -> str:
    """Convert a wildcard pattern (with *) to a regex pattern."""
    # Escape special regex characters except *
    escaped = re.escape(pattern)
    # Convert escaped \* back to .*
    return escaped.replace(r'\*', '.*')


def process_backspaces(text: str) -> str:
    """
    Process backspace characters to reveal the actual rendered text.

    Spammers sometimes output "Ge\x08\x08ek" which renders as "ek" but
    hides the word "Geek" from simple pattern matching.
    """
    result = []
    for char in text:
        if char == '\x08':  # Backspace
            if result:
                result.pop()
        else:
            result.append(char)
    return ''.join(result)


def normalize_homoglyphs(text: str) -> str:
    """
    Normalize Unicode homoglyphs to ASCII equivalents.

    Converts characters like "Géék Sqüád" to "Geek Squad" by:
    1. Decomposing characters (NFKD normalization)
    2. Removing combining marks (accents, diacritics)
    3. Keeping only ASCII-compatible characters
    """
    # NFKD normalization decomposes characters
    # e.g., "é" becomes "e" + combining acute accent
    normalized = unicodedata.normalize('NFKD', text)

    # Remove combining characters (category 'M' = Mark)
    # This strips accents and diacritics
    result = []
    for char in normalized:
        if unicodedata.category(char) != 'Mn':  # Mn = Mark, Nonspacing
            # Try to keep ASCII equivalents
            try:
                char.encode('ascii')
                result.append(char)
            except UnicodeEncodeError:
                # For characters that still aren't ASCII after normalization,
                # try common replacements
                replacements = {
                    'ø': 'o', 'Ø': 'O',
                    'ß': 'ss',
                    'æ': 'ae', 'Æ': 'AE',
                    'œ': 'oe', 'Œ': 'OE',
                    'đ': 'd', 'Đ': 'D',
                    'ł': 'l', 'Ł': 'L',
                    '€': 'E',
                    '£': 'L',
                    '¥': 'Y',
                }
                result.append(replacements.get(char, char))

    return ''.join(result)


def scrub_text(text: str) -> str:
    """
    Apply all spam-evasion countermeasures to text.

    Combines backspace processing and homoglyph normalization.
    """
    if not text:
        return text
    text = process_backspaces(text)
    text = normalize_homoglyphs(text)
    return text
