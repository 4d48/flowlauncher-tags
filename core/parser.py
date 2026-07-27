from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol, Self

from core.lexer import Lexer, Token, TokenType


class ParserError(ValueError):
    """Exception raised when an error occurs during parsing."""

    pass


class Command(Protocol):
    """Base protocol class for parsed command objects."""

    pass


class EmptyCommand(Command):
    """Represents an empty or unspecified command."""

    pass


@dataclass(frozen=True)
class GetProgramsByTag(Command):
    """Command to retrieve programs associated with a specific tag."""

    tag_name: str


@dataclass(frozen=True)
class AddTag(Command):
    """Command to add a tag to a program."""

    tag_name: str
    program_name: str


@dataclass(frozen=True)
class RemoveTag(Command):
    """Command to remove a tag from a program."""

    tag_name: str
    program_name: str


class AutocompleteType(Enum):
    """Enum representing categories of autocompletion context."""

    COMMAND = auto()
    TAG = auto()
    PROGRAM = auto()
    ADD_TAG_PROGRAM = auto()
    REMOVE_TAG_PROGRAM = auto()
    NOTHING = auto()


@dataclass(frozen=True)
class AutocompleteContext:
    """Context information for autocompletion logic."""

    type: list[AutocompleteType]
    prefix: str
    args: dict[str, str]


@dataclass(frozen=True)
class ParserResult:
    """Result of parsing containing the parsed command and autocomplete context."""

    command: Command | None
    autocomplete_context: AutocompleteContext


class GrammarNodeType(Enum):
    """Enum representing grammar node types in the parsing state machine."""

    ROOT = auto()
    SPACE = auto()
    TAG = auto()
    PROGRAM = auto()
    OP_ADD = auto()
    OP_REM = auto()

    @property
    def token_type(self) -> TokenType:
        """Map the grammar node type to its corresponding TokenType.

        Returns:
            The TokenType associated with current node type.
        """
        mapping = {
            GrammarNodeType.ROOT: TokenType.NOTHING,
            GrammarNodeType.SPACE: TokenType.SPACE,
            GrammarNodeType.TAG: TokenType.IDENTIFIER,
            GrammarNodeType.PROGRAM: TokenType.IDENTIFIER,
            GrammarNodeType.OP_ADD: TokenType.OP_ADD,
            GrammarNodeType.OP_REM: TokenType.OP_REM,
        }
        return mapping[self]


class GrammarNode:
    """Represents a node in the grammar transition tree. Grammar represents a parser state machine"""

    def __init__(
        self,
        command: type[Command],
        node_type: GrammarNodeType,
        autocomplete_type_list: list[AutocompleteType],
        is_last: bool = False,
    ) -> None:
        """Initialize a GrammarNode.

        Args:
            command: The Command class associated with current node.
            node_type: The GrammarNodeType defining the expected token type for current node.
            autocomplete_type_list: Autocomplete categories applicable at current node.
            is_last: Whether current node represents a complete valid command.
        """
        self.command: type[Command] = command
        self.semantic_role: str = node_type.name
        self.expected_token_type: TokenType = node_type.token_type
        self.autocomplete_type_list: list[AutocompleteType] = autocomplete_type_list
        self.is_last: bool = is_last
        self.children: list[Self] = []

    def add_child(self, child_node: Self):
        """Add a child node to current grammar node.

        Args:
            child_node: The child GrammarNode to add.
        """
        self.children.append(child_node)

    def add_child_and_return(self, child_node: Self) -> Self:
        """Add a child node to current grammar node and return the child node.

        Args:
            child_node: The child GrammarNode to add.

        Returns:
            The added child GrammarNode instance.
        """
        self.children.append(child_node)
        return self.children[-1]

    def next_node(self, token_type: TokenType) -> Self | None:
        """Find the child node expecting the specified token type.

        Args:
            token_type: The TokenType to match among children.

        Returns:
            The matching child GrammarNode or None if no match exists.
        """
        for child in self.children:
            if token_type == child.expected_token_type:
                return child

        return None

    def set_last(self):
        """Mark current grammar node as a valid terminal node for a command."""
        self.is_last = True


# fmt: off
grammar: GrammarNode = GrammarNode(
    EmptyCommand, GrammarNodeType.ROOT, [AutocompleteType.COMMAND, AutocompleteType.TAG]
)

grammar.add_child_and_return(
    GrammarNode(GetProgramsByTag,        GrammarNodeType.TAG,    [AutocompleteType.TAG])
).set_last()
grammar.add_child(GrammarNode(AddTag,    GrammarNodeType.OP_ADD, [AutocompleteType.TAG]))
grammar.add_child(GrammarNode(RemoveTag, GrammarNodeType.OP_REM, [AutocompleteType.TAG]))

(
grammar.next_node(TokenType.OP_ADD)
    .add_child_and_return(GrammarNode(AddTag, GrammarNodeType.SPACE,   [AutocompleteType.TAG])) # pyright: ignore[reportOptionalMemberAccess]
    .add_child_and_return(GrammarNode(AddTag, GrammarNodeType.TAG,     [AutocompleteType.TAG]))
    .add_child_and_return(GrammarNode(AddTag, GrammarNodeType.SPACE,   [AutocompleteType.ADD_TAG_PROGRAM]))
    .add_child_and_return(GrammarNode(AddTag, GrammarNodeType.PROGRAM, [AutocompleteType.ADD_TAG_PROGRAM]))
    .set_last()
)

(
grammar.next_node(TokenType.OP_REM)
    .add_child_and_return(GrammarNode(RemoveTag, GrammarNodeType.SPACE,   [AutocompleteType.TAG])) # pyright: ignore[reportOptionalMemberAccess]
    .add_child_and_return(GrammarNode(RemoveTag, GrammarNodeType.TAG,     [AutocompleteType.TAG]))
    .add_child_and_return(GrammarNode(RemoveTag, GrammarNodeType.SPACE,   [AutocompleteType.REMOVE_TAG_PROGRAM]))
    .add_child_and_return(GrammarNode(RemoveTag, GrammarNodeType.PROGRAM, [AutocompleteType.REMOVE_TAG_PROGRAM]))
    .set_last()
)
# fmt: on


class Parser:
    """Parser for converting tokens into executable commands and autocomplete context."""

    def __init__(self) -> None:
        """Initialize the Parser state."""
        self.current_grammar_node: GrammarNode = grammar
        self.command_args: dict[str, str] = {}
        self.current_token: Token = Token(TokenType.NOTHING, "")

    def parse_token(self, token: Token) -> None:
        """Process a single token to advance the parsing state machine.

        Args:
            token: The Token instance to process.
        """
        if token.type == TokenType.NOTHING:
            return

        next_node = self.current_grammar_node.next_node(token.type)

        if not next_node:
            return

        self.current_grammar_node = next_node

        self.current_token = token

        match self.current_grammar_node.semantic_role:
            case GrammarNodeType.TAG.name:
                self.command_args["tag_name"] = token.value
            case GrammarNodeType.PROGRAM.name:
                self.command_args["program_name"] = token.value
            case _:
                pass

    @property
    def autocomplete_context(self) -> AutocompleteContext:
        """Generate the current AutocompleteContext based on parser state.

        Returns:
            The current AutocompleteContext object.
        """
        if self.current_grammar_node.semantic_role.startswith("OP_"):
            prefix = ""
        else:
            prefix = (
                self.current_token.value.strip()
            )  # strip() in case the value is space

        return AutocompleteContext(
            self.current_grammar_node.autocomplete_type_list,
            prefix,
            self.command_args.copy(),
        )

    def get_result(self) -> ParserResult:
        """Build the final ParserResult from current parser state.

        Returns:
            The ParserResult containing optional command and autocomplete context.
        """
        command_cls = self.current_grammar_node.command

        if self.current_grammar_node.is_last:
            command = command_cls(**self.command_args)
        else:
            command = None

        return ParserResult(command, self.autocomplete_context)


def parse_input(input: str) -> ParserResult:
    """Parse an input string into a ParserResult.

    Args:
        input: The raw input string to parse.

    Returns:
        The resulting ParserResult containing command and autocomplete context.
    """
    lexer = Lexer(input)
    parser = Parser()

    for token in lexer.tokens:
        print(token)
        parser.parse_token(token)

    return parser.get_result()
