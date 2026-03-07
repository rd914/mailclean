"""Parser for the query language."""

from typing import Iterator

from .lexer import Lexer, Token, TokenType, LexerError
from .criteria import (
    Criterion,
    FromCriterion,
    ToCriterion,
    CcCriterion,
    BccCriterion,
    AddresseeCriterion,
    DateCriterion,
    BeforeCriterion,
    AfterCriterion,
    OlderThanCriterion,
    NewerThanCriterion,
    SubjectCriterion,
    BodyCriterion,
    TextCriterion,
    HeaderCriterion,
    AndCriterion,
    OrCriterion,
    NotCriterion,
)


class ParseError(Exception):
    """Error during parsing."""

    def __init__(self, message: str, position: int = 0):
        self.message = message
        self.position = position
        super().__init__(f"{message} at position {position}")


CRITERION_MAP = {
    'from': FromCriterion,
    'to': ToCriterion,
    'cc': CcCriterion,
    'bcc': BccCriterion,
    'addressee': AddresseeCriterion,
    'date': DateCriterion,
    'before': BeforeCriterion,
    'after': AfterCriterion,
    'older-than': OlderThanCriterion,
    'newer-than': NewerThanCriterion,
    'subject': SubjectCriterion,
    'body': BodyCriterion,
    'text': TextCriterion,
}


class Parser:
    """
    Recursive descent parser for the query language.

    Grammar:
        query       ::= or_expr
        or_expr     ::= and_expr (OR and_expr)*
        and_expr    ::= not_expr (AND not_expr)*
        not_expr    ::= NOT not_expr | primary
        primary     ::= LPAREN query RPAREN | criterion
        criterion   ::= KEYWORD COLON VALUE
    """

    def __init__(self, text: str):
        self.text = text
        self.tokens: list[Token] = []
        self.pos = 0

    def parse(self) -> Criterion:
        """Parse the query string into a criterion tree."""
        try:
            lexer = Lexer(self.text)
            self.tokens = list(lexer.tokenize())
        except LexerError as e:
            raise ParseError(e.message, e.position) from e

        self.pos = 0

        if self._current_token().type == TokenType.EOF:
            raise ParseError("Empty query", 0)

        result = self._parse_or_expr()

        if self._current_token().type != TokenType.EOF:
            raise ParseError(
                f"Unexpected token: {self._current_token().value}",
                self._current_token().position
            )

        return result

    def _current_token(self) -> Token:
        if self.pos >= len(self.tokens):
            return Token(TokenType.EOF, '', len(self.text))
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        token = self._current_token()
        self.pos += 1
        return token

    def _expect(self, token_type: TokenType) -> Token:
        token = self._current_token()
        if token.type != token_type:
            raise ParseError(
                f"Expected {token_type.name}, got {token.type.name}",
                token.position
            )
        return self._advance()

    def _parse_or_expr(self) -> Criterion:
        """Parse OR expressions."""
        left = self._parse_and_expr()

        while self._current_token().type == TokenType.OR:
            self._advance()  # Skip OR
            right = self._parse_and_expr()
            left = OrCriterion(left, right)

        return left

    def _parse_and_expr(self) -> Criterion:
        """Parse AND expressions."""
        left = self._parse_not_expr()

        while self._current_token().type == TokenType.AND:
            self._advance()  # Skip AND
            right = self._parse_not_expr()
            left = AndCriterion(left, right)

        # Handle implicit AND (adjacent criteria without explicit AND)
        while self._current_token().type in (TokenType.KEYWORD, TokenType.NOT, TokenType.LPAREN):
            right = self._parse_not_expr()
            left = AndCriterion(left, right)

        return left

    def _parse_not_expr(self) -> Criterion:
        """Parse NOT expressions."""
        if self._current_token().type == TokenType.NOT:
            self._advance()  # Skip NOT
            criterion = self._parse_not_expr()
            return NotCriterion(criterion)

        return self._parse_primary()

    def _parse_primary(self) -> Criterion:
        """Parse primary expressions (parenthesized or criteria)."""
        token = self._current_token()

        if token.type == TokenType.LPAREN:
            self._advance()  # Skip (
            result = self._parse_or_expr()
            self._expect(TokenType.RPAREN)
            return result

        if token.type == TokenType.KEYWORD:
            return self._parse_criterion()

        raise ParseError(
            f"Unexpected token: {token.value}",
            token.position
        )

    def _parse_criterion(self) -> Criterion:
        """Parse a single criterion (keyword:value)."""
        keyword_token = self._expect(TokenType.KEYWORD)
        self._expect(TokenType.COLON)
        value_token = self._expect(TokenType.VALUE)

        keyword = keyword_token.value.lower()
        value = value_token.value

        if keyword not in CRITERION_MAP:
            # Treat as an arbitrary email header criterion
            return HeaderCriterion(keyword, value)

        criterion_class = CRITERION_MAP[keyword]

        try:
            return criterion_class(value)
        except ValueError as e:
            raise ParseError(str(e), value_token.position) from e


def parse_query(text: str) -> Criterion:
    """Parse a query string into a criterion tree."""
    parser = Parser(text)
    return parser.parse()
