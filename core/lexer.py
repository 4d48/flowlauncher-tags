from dataclasses import dataclass
from enum import StrEnum, auto


class CommandKeyword(StrEnum):
    """Enum representing supported command keywords."""

    ADD_TAG = "add"
    REMOVE_TAG = "remove"


class TokenType(StrEnum):
    """Enum representing lexer token types."""

    NOTHING = auto()
    SPACE = auto()
    IDENTIFIER = auto()
    OP_ADD = auto()
    OP_REM = auto()


@dataclass(frozen=True)
class Token:
    """Represents a lexical token with a type and text value."""

    type: TokenType
    value: str


class Lexer:
    """Lexer for tokenizing query strings."""

    def __init__(self, input: str) -> None:
        """Initialize the Lexer with an input string.

        Args:
            input: The query input string without plugin keyword and not stripped.
        """
        self.input: str = input.lstrip()

    @property
    def tokens(self):
        """Yield tokens parsed from the input string.

        Yields:
            Token: Next token extracted from the input string.
        """
        parts = self.input.split(maxsplit=2)

        if not parts:
            yield Token(TokenType.NOTHING, "")
            return

        current_idx = 0
        for part in parts:
            part_idx = self.input.find(part, current_idx)

            if part_idx > current_idx:
                yield Token(TokenType.SPACE, " ")

            match part:
                case CommandKeyword.ADD_TAG:
                    yield Token(TokenType.OP_ADD, part)
                case CommandKeyword.REMOVE_TAG:
                    yield Token(TokenType.OP_REM, part)
                case _:
                    yield Token(TokenType.IDENTIFIER, part)

            current_idx = part_idx + len(part)

        if current_idx < len(self.input):
            yield Token(TokenType.SPACE, " ")
