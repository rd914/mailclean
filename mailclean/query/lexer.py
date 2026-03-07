"""Lexer for the query language."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    """Token types for the query language."""

    KEYWORD = auto()      # from, to, cc, bcc, addressee, date, before, after, etc.
    COLON = auto()        # :
    VALUE = auto()        # The value after a keyword
    AND = auto()          # AND
    OR = auto()           # OR
    NOT = auto()          # NOT
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    EOF = auto()          # End of input


@dataclass
class Token:
    """A token from the lexer."""

    type: TokenType
    value: str
    position: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r})"


KEYWORDS = {
    'from', 'to', 'cc', 'bcc', 'addressee',
    'date', 'before', 'after', 'older-than', 'newer-than',
    'subject', 'body',
}


class LexerError(Exception):
    """Error during lexing."""

    def __init__(self, message: str, position: int):
        self.message = message
        self.position = position
        super().__init__(f"{message} at position {position}")


class Lexer:
    """Tokenizer for the query language."""

    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.length = len(text)

    def _current_char(self) -> str | None:
        if self.pos >= self.length:
            return None
        return self.text[self.pos]

    def _peek(self, offset: int = 1) -> str | None:
        pos = self.pos + offset
        if pos >= self.length:
            return None
        return self.text[pos]

    def _advance(self) -> str | None:
        char = self._current_char()
        self.pos += 1
        return char

    def _skip_whitespace(self) -> None:
        while self._current_char() and self._current_char().isspace():
            self._advance()

    def _read_word(self) -> str:
        """Read a word (alphanumeric plus hyphen)."""
        result = []
        while self._current_char() and (self._current_char().isalnum() or self._current_char() == '-'):
            result.append(self._advance())
        return ''.join(result)

    def _read_value(self) -> str:
        """Read a value after a colon."""
        result = []

        # Handle quoted values
        if self._current_char() == '"':
            self._advance()  # Skip opening quote
            while self._current_char() and self._current_char() != '"':
                if self._current_char() == '\\' and self._peek() == '"':
                    self._advance()  # Skip backslash
                result.append(self._advance())
            if self._current_char() == '"':
                self._advance()  # Skip closing quote
            return ''.join(result)

        # Handle regex values /pattern/flags
        if self._current_char() == '/':
            result.append(self._advance())  # Opening /
            while self._current_char() and self._current_char() != '/':
                if self._current_char() == '\\':
                    result.append(self._advance())  # Include backslash
                if self._current_char():
                    result.append(self._advance())
            if self._current_char() == '/':
                result.append(self._advance())  # Closing /
                # Read flags
                while self._current_char() and self._current_char().isalpha():
                    result.append(self._advance())
            return ''.join(result)

        # Unquoted value - read until whitespace or paren
        while self._current_char() and not self._current_char().isspace() and self._current_char() not in '()':
            result.append(self._advance())

        return ''.join(result)

    def tokenize(self) -> Iterator[Token]:
        """Tokenize the input string."""
        while True:
            self._skip_whitespace()

            if self._current_char() is None:
                yield Token(TokenType.EOF, '', self.pos)
                return

            start_pos = self.pos
            char = self._current_char()

            # Parentheses
            if char == '(':
                self._advance()
                yield Token(TokenType.LPAREN, '(', start_pos)
                continue

            if char == ')':
                self._advance()
                yield Token(TokenType.RPAREN, ')', start_pos)
                continue

            # Read a word
            word = self._read_word()
            if not word:
                raise LexerError(f"Unexpected character: {char}", start_pos)

            word_upper = word.upper()

            # Check for boolean operators
            if word_upper == 'AND':
                yield Token(TokenType.AND, 'AND', start_pos)
                continue

            if word_upper == 'OR':
                yield Token(TokenType.OR, 'OR', start_pos)
                continue

            if word_upper == 'NOT':
                yield Token(TokenType.NOT, 'NOT', start_pos)
                continue

            # Any word followed by colon is a keyword (known field or arbitrary header)
            word_lower = word.lower()
            self._skip_whitespace()
            if self._current_char() == ':':
                self._advance()  # Skip colon
                self._skip_whitespace()
                value = self._read_value()
                yield Token(TokenType.KEYWORD, word_lower, start_pos)
                yield Token(TokenType.COLON, ':', self.pos)
                yield Token(TokenType.VALUE, value, self.pos)
                continue

            raise LexerError(f"Unexpected token: {word!r} (expected keyword:value)", start_pos)
