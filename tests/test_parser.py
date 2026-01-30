"""Tests for the query parser."""

import pytest

from mailclean.query.parser import Parser, ParseError, parse_query
from mailclean.query.criteria import (
    FromCriterion, ToCriterion, CcCriterion, BccCriterion, AddresseeCriterion,
    DateCriterion, BeforeCriterion, AfterCriterion,
    OlderThanCriterion, NewerThanCriterion,
    SubjectCriterion, BodyCriterion,
    AndCriterion, OrCriterion, NotCriterion,
)


class TestParser:
    """Tests for the Parser class."""

    def test_simple_from_criterion(self):
        """Test parsing a simple from criterion."""
        criterion = parse_query("from:user@example.com")

        assert isinstance(criterion, FromCriterion)
        assert criterion.pattern == "user@example.com"

    def test_all_simple_criteria(self):
        """Test parsing all simple criteria types."""
        tests = [
            ("from:a@b.com", FromCriterion),
            ("to:a@b.com", ToCriterion),
            ("cc:a@b.com", CcCriterion),
            ("bcc:a@b.com", BccCriterion),
            ("addressee:a@b.com", AddresseeCriterion),
            ("date:2024-01-01", DateCriterion),
            ("before:2024-01-01", BeforeCriterion),
            ("after:2024-01-01", AfterCriterion),
            ("older-than:30d", OlderThanCriterion),
            ("newer-than:1w", NewerThanCriterion),
            ("subject:/test/i", SubjectCriterion),
            ("body:/unsubscribe/", BodyCriterion),
        ]

        for query, expected_type in tests:
            criterion = parse_query(query)
            assert isinstance(criterion, expected_type), f"Failed for query: {query}"

    def test_and_expression(self):
        """Test parsing AND expressions."""
        criterion = parse_query("from:a@b.com AND to:c@d.com")

        assert isinstance(criterion, AndCriterion)
        assert isinstance(criterion.left, FromCriterion)
        assert isinstance(criterion.right, ToCriterion)

    def test_or_expression(self):
        """Test parsing OR expressions."""
        criterion = parse_query("from:a@b.com OR from:c@d.com")

        assert isinstance(criterion, OrCriterion)
        assert isinstance(criterion.left, FromCriterion)
        assert isinstance(criterion.right, FromCriterion)

    def test_not_expression(self):
        """Test parsing NOT expressions."""
        criterion = parse_query("NOT from:spam@example.com")

        assert isinstance(criterion, NotCriterion)
        assert isinstance(criterion.criterion, FromCriterion)

    def test_parentheses(self):
        """Test parsing parenthesized expressions."""
        criterion = parse_query("(from:a@b.com OR from:c@d.com) AND older-than:30d")

        assert isinstance(criterion, AndCriterion)
        assert isinstance(criterion.left, OrCriterion)
        assert isinstance(criterion.right, OlderThanCriterion)

    def test_operator_precedence(self):
        """Test that AND has higher precedence than OR."""
        # "a OR b AND c" should parse as "a OR (b AND c)"
        criterion = parse_query("from:a@b.com OR from:b@c.com AND to:d@e.com")

        assert isinstance(criterion, OrCriterion)
        assert isinstance(criterion.left, FromCriterion)
        assert isinstance(criterion.right, AndCriterion)

    def test_multiple_and(self):
        """Test multiple AND operators."""
        criterion = parse_query("from:a@b.com AND to:c@d.com AND older-than:30d")

        assert isinstance(criterion, AndCriterion)
        assert isinstance(criterion.left, AndCriterion)
        assert isinstance(criterion.right, OlderThanCriterion)

    def test_multiple_or(self):
        """Test multiple OR operators."""
        criterion = parse_query("from:a@b.com OR from:b@c.com OR from:c@d.com")

        assert isinstance(criterion, OrCriterion)
        assert isinstance(criterion.left, OrCriterion)
        assert isinstance(criterion.right, FromCriterion)

    def test_nested_parentheses(self):
        """Test nested parentheses."""
        criterion = parse_query("((from:a@b.com OR from:b@c.com) AND to:d@e.com)")

        assert isinstance(criterion, AndCriterion)
        assert isinstance(criterion.left, OrCriterion)
        assert isinstance(criterion.right, ToCriterion)

    def test_complex_query(self):
        """Test a complex real-world query."""
        query = "(from:*@spam.com OR from:*@ads.com) AND older-than:90d AND NOT subject:/important/i"
        criterion = parse_query(query)

        assert isinstance(criterion, AndCriterion)
        # The structure should be ((from OR from) AND older-than) AND NOT subject

    def test_implicit_and(self):
        """Test implicit AND between adjacent criteria."""
        criterion = parse_query("from:a@b.com to:c@d.com")

        assert isinstance(criterion, AndCriterion)
        assert isinstance(criterion.left, FromCriterion)
        assert isinstance(criterion.right, ToCriterion)

    def test_empty_query_raises_error(self):
        """Test that empty query raises error."""
        with pytest.raises(ParseError):
            parse_query("")

    def test_unclosed_paren_raises_error(self):
        """Test that unclosed parenthesis raises error."""
        with pytest.raises(ParseError):
            parse_query("(from:a@b.com")

    def test_invalid_date_raises_error(self):
        """Test that invalid date raises error."""
        with pytest.raises(ParseError):
            parse_query("date:not-a-date")

    def test_invalid_relative_date_raises_error(self):
        """Test that invalid relative date raises error."""
        with pytest.raises(ParseError):
            parse_query("older-than:xyz")

    def test_double_not(self):
        """Test double NOT."""
        criterion = parse_query("NOT NOT from:a@b.com")

        assert isinstance(criterion, NotCriterion)
        assert isinstance(criterion.criterion, NotCriterion)
        assert isinstance(criterion.criterion.criterion, FromCriterion)
