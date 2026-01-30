"""Evaluate queries against email messages."""

from typing import TYPE_CHECKING

from .parser import parse_query
from .criteria import Criterion

if TYPE_CHECKING:
    from ..models import EmailMessage


def evaluate_query(query: str, email: 'EmailMessage') -> bool:
    """
    Evaluate a query string against an email message.

    Args:
        query: The query string to evaluate
        email: The email message to check

    Returns:
        True if the email matches the query, False otherwise
    """
    criterion = parse_query(query)
    return criterion.matches(email)


def compile_query(query: str) -> Criterion:
    """
    Compile a query string into a criterion tree.

    This is useful when evaluating the same query against many emails,
    as it avoids re-parsing the query for each email.

    Args:
        query: The query string to compile

    Returns:
        A Criterion object that can be used to match emails
    """
    return parse_query(query)
