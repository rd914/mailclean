"""Tests for the query lexer."""

import pytest

from mailclean.query.lexer import Lexer, Token, TokenType, LexerError


class TestLexer:
    """Tests for the Lexer class."""

    def test_simple_keyword_value(self):
        """Test lexing a simple keyword:value."""
        lexer = Lexer("from:user@example.com")
        tokens = list(lexer.tokenize())

        assert len(tokens) == 4  # KEYWORD, COLON, VALUE, EOF
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "from"
        assert tokens[1].type == TokenType.COLON
        assert tokens[2].type == TokenType.VALUE
        assert tokens[2].value == "user@example.com"
        assert tokens[3].type == TokenType.EOF

    def test_wildcard_value(self):
        """Test lexing a wildcard pattern."""
        lexer = Lexer("from:*@spam.com")
        tokens = list(lexer.tokenize())

        assert tokens[2].value == "*@spam.com"

    def test_and_operator(self):
        """Test lexing AND operator."""
        lexer = Lexer("from:a@b.com AND to:c@d.com")
        tokens = list(lexer.tokenize())

        assert tokens[3].type == TokenType.AND
        assert tokens[3].value == "AND"

    def test_or_operator(self):
        """Test lexing OR operator."""
        lexer = Lexer("from:a@b.com OR from:b@c.com")
        tokens = list(lexer.tokenize())

        assert tokens[3].type == TokenType.OR
        assert tokens[3].value == "OR"

    def test_not_operator(self):
        """Test lexing NOT operator."""
        lexer = Lexer("NOT from:spam@example.com")
        tokens = list(lexer.tokenize())

        assert tokens[0].type == TokenType.NOT
        assert tokens[0].value == "NOT"

    def test_parentheses(self):
        """Test lexing parentheses."""
        lexer = Lexer("(from:a@b.com OR from:c@d.com)")
        tokens = list(lexer.tokenize())

        assert tokens[0].type == TokenType.LPAREN
        assert tokens[8].type == TokenType.RPAREN

    def test_date_keyword(self):
        """Test lexing date-related keywords."""
        lexer = Lexer("older-than:30d")
        tokens = list(lexer.tokenize())

        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "older-than"
        assert tokens[2].value == "30d"

    def test_regex_value(self):
        """Test lexing regex pattern values."""
        lexer = Lexer("subject:/newsletter/i")
        tokens = list(lexer.tokenize())

        assert tokens[2].value == "/newsletter/i"

    def test_quoted_value(self):
        """Test lexing quoted values."""
        lexer = Lexer('from:"John Doe <john@example.com>"')
        tokens = list(lexer.tokenize())

        assert tokens[2].value == "John Doe <john@example.com>"

    def test_case_insensitive_operators(self):
        """Test that AND/OR/NOT are case insensitive."""
        for op in ["and", "AND", "And", "aNd"]:
            lexer = Lexer(f"from:a@b.com {op} to:c@d.com")
            tokens = list(lexer.tokenize())
            assert tokens[3].type == TokenType.AND

    def test_all_keywords(self):
        """Test all supported keywords."""
        keywords = [
            "from", "to", "cc", "bcc", "addressee",
            "date", "before", "after", "older-than", "newer-than",
            "subject", "body"
        ]

        for keyword in keywords:
            lexer = Lexer(f"{keyword}:value")
            tokens = list(lexer.tokenize())
            assert tokens[0].type == TokenType.KEYWORD
            assert tokens[0].value == keyword

    def test_unknown_keyword_raises_error(self):
        """Test that unknown keywords raise an error."""
        lexer = Lexer("unknown:value")

        with pytest.raises(LexerError) as exc_info:
            list(lexer.tokenize())

        assert "unknown" in str(exc_info.value).lower()

    def test_complex_query(self):
        """Test lexing a complex query."""
        query = "(from:*@spam.com OR from:*@ads.com) AND older-than:90d AND NOT subject:/important/i"
        lexer = Lexer(query)
        tokens = list(lexer.tokenize())

        # Verify structure
        token_types = [t.type for t in tokens]
        assert TokenType.LPAREN in token_types
        assert TokenType.RPAREN in token_types
        assert token_types.count(TokenType.AND) == 2
        assert TokenType.OR in token_types
        assert TokenType.NOT in token_types

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        # Extra whitespace should be ignored
        lexer = Lexer("  from:a@b.com   AND   to:c@d.com  ")
        tokens = list(lexer.tokenize())

        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[3].type == TokenType.AND
