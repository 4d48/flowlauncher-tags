import sys
from pathlib import Path

plugindir = Path.absolute(Path(__file__).parent)
sys.path.insert(0, str(plugindir / "lib"))

from collections.abc import Iterable

from flogin import (
    Glyph,
    Plugin,
    Query,
    Result,
)

from config import (
    ICON_CACHE_DIR,
    ICON_MISSING_PATH,
    MAX_SCORE,
    TAGS_FILE_PATH,
    logger,
)
from core.lexer import CommandKeyword, Lexer
from core.parser import (
    AddTag,
    AutocompleteContext,
    AutocompleteType,
    GetProgramsByTag,
    Parser,
    RemoveTag,
)
from core.program_manager import ProgramManager
from core.programs import Program
from core.tag_manager import TagManager
from ui.results import (
    AddTagToProgramResult,
    ChangeQueryResult,
    LaunchProgramResult,
    RemoveTagFromProgramResult,
    RemoveTagResult,
)


class TagsPlugin(Plugin):
    """Flow Launcher plugin for managing and querying program tags."""

    def __init__(self):
        """Initialize the TagsPlugin instance."""
        super().__init__()
        self.program_manager: ProgramManager
        self.tag_manager: TagManager

    @Plugin.event  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
    async def on_initialization(self):
        """Handle plugin initialization by scanning programs, caching icons, and loading tags."""
        self.program_manager = ProgramManager.from_os()

        for program in self.program_manager.programs:
            cached_icon_path = ICON_CACHE_DIR / f"{(program.sha256()[:16])}.png"

            if not cached_icon_path.exists():
                _ = program.icon_to_file(cached_icon_path, ICON_MISSING_PATH)

        try:
            self.tag_manager = TagManager.from_file(TAGS_FILE_PATH)
            logger.info("Loaded tags from file")
        except Exception as e:
            logger.exception("Failed to load tags from file: %s", e)
            self.tag_manager = TagManager()

    @Plugin.search()
    async def search_handler(self, query: Query[None]) -> list[Result]:
        """Handle incoming search queries from Flow Launcher and return matching results.

        Args:
            query: The Query object containing user input.

        Returns:
            A list of Result objects to display in Flow Launcher.
        """
        logger.debug("Query: %r", query)

        results: list[Result] = []

        text = query.text

        if query.original_query.endswith(" "):
            text += " "

        lexer = Lexer(text)
        parser = Parser()

        for token in lexer.tokens:
            parser.parse_token(token)

        parser_result = parser.get_result()

        context: AutocompleteContext = parser_result.autocomplete_context
        base_query: str = self.get_base_query(query.original_query, context.prefix)

        if not parser_result.command:
            results.extend(self.autocomplete(base_query, context))
            return results

        match parser_result.command:
            case GetProgramsByTag():
                results.extend(self.autocomplete_command(base_query, context.prefix))
                results.extend(self.autocomplete_tag(base_query, context.prefix))
                results.extend(self.get_programs_by_tag(parser_result.command.tag_name))
            case AddTag() | RemoveTag():
                results.extend(self.autocomplete(base_query, context))
            case _:
                pass

        return results

    def get_program_icon(self, program: Program) -> str:
        """Retrieve the cached icon path for a program or return a fallback icon path.

        Args:
            program: The Program instance to get the icon for.

        Returns:
            The path string of the program icon or default missing icon.
        """
        cached_icon_path = ICON_CACHE_DIR / f"{program.sha256()[:16]}.png"

        if cached_icon_path.exists():
            return str(cached_icon_path)

        return str(ICON_MISSING_PATH)

    def get_programs_by_tag(self, tag: str) -> list[Result]:
        """Retrieve launch result items for programs associated with a given tag.

        Args:
            tag: The tag name to filter programs by.

        Returns:
            A list of LaunchProgramResult objects for matching programs.
        """
        result: list[Result] = []

        for program in self.tag_manager.search_by_tag(tag):
            result.append(
                LaunchProgramResult(
                    title=f"{program.name}",
                    query_suggestion_text=f"{program.name}",
                    icon=self.get_program_icon(program),
                    program=program,
                    api=self.api,
                )
            )

        return result

    def get_programs_add_tag_action(self, tag: str, prefix: str) -> list[Result]:
        """Generate result actions for adding a tag to matching programs.

        Args:
            tag: The tag name to add.
            prefix: Search prefix filter for program names.

        Returns:
            A list of AddTagToProgramResult objects.
        """
        results: list[Result] = []

        programs_by_tag: set[Program] = self.tag_manager.search_by_tag(tag)

        programs_found: set[Program] = (
            self.program_manager.find(prefix) - programs_by_tag
        )

        for program in programs_found:
            results.append(
                AddTagToProgramResult(
                    title=f"{program.name}",
                    query_suggestion_text=f"{program.name}",
                    icon=self.get_program_icon(program),
                    tag=tag,
                    program=program,
                    tag_manager=self.tag_manager,
                    api=self.api,
                )
            )

        return results

    def get_programs_remove_tag_action(self, tag: str, prefix: str) -> list[Result]:
        """Generate result actions for removing a tag from tagged programs.

        Args:
            tag: The tag name to remove.
            prefix: Search prefix filter for program names.

        Returns:
            A list of RemoveTagFromProgramResult objects.
        """
        results: list[Result] = []

        results.append(
            RemoveTagResult(
                title="Remove entire tag",
                query_suggestion_text=f"{tag}",
                glyph=Glyph(text="✕", font_family="Segoe UI"),
                score=MAX_SCORE,
                tag=tag,
                tag_manager=self.tag_manager,
                api=self.api,
            )
        )

        programs_by_tag: set[Program] = self.tag_manager.search_by_tag(tag)

        if prefix:
            programs_found: set[Program] = self.program_manager.find(
                prefix, programs_by_tag
            )
        else:
            programs_found = programs_by_tag

        for program in programs_found:
            results.append(
                RemoveTagFromProgramResult(
                    title=f"{program.name}",
                    query_suggestion_text=f"{program.name}",
                    icon=self.get_program_icon(program),
                    tag=tag,
                    tag_manager=self.tag_manager,
                    program=program,
                    api=self.api,
                )
            )

        return results

    def autocomplete_command(self, base_query: str, prefix: str) -> list[Result]:
        """Generate autocomplete suggestion results for available commands.

        Args:
            base_query: The base query prefix string.

        Returns:
            A list of ChangeQueryResult objects for available tag commands.
        """
        result: list[Result] = []

        for command in CommandKeyword:
            if command.value.startswith(prefix):
                result.append(
                    ChangeQueryResult(
                        title=command.result_title,
                        query_suggestion_text=f"{command.value}",
                        glyph=Glyph(text=">", font_family="Segoe UI"),
                        score=MAX_SCORE,
                        new_query=f"{base_query}{command.value} ",
                        api=self.api,
                    )
                )

        return result

    def autocomplete_tag(self, base_query: str, prefix: str) -> list[Result]:
        """Generate autocomplete suggestion results for existing tags matching a prefix.

        Args:
            base_query: The base query prefix string.
            prefix: The tag prefix to match.

        Returns:
            A list of ChangeQueryResult objects for matching tags.
        """
        results: list[Result] = []

        for tag in self.tag_manager.tags:
            if tag != prefix and tag.startswith(prefix):
                results.append(
                    ChangeQueryResult(
                        title=f"{tag}",
                        query_suggestion_text=f"{tag}",
                        glyph=Glyph(text="#", font_family="Segoe UI"),
                        new_query=f"{base_query}{tag} ",
                        api=self.api,
                    )
                )

        return results

    def autocomplete_program(self, base_query: str, prefix: str) -> list[Result]:
        """Generate autocomplete suggestion results for programs matching a prefix.

        Args:
            base_query: The base query prefix string.
            prefix: The program name prefix to match.

        Returns:
            A list of ChangeQueryResult objects for matching programs.
        """
        results: list[Result] = []

        if prefix:
            programs_found: Iterable[Program] = self.program_manager.find(prefix)
        else:
            programs_found = self.program_manager.programs

        for program in programs_found:
            results.append(
                ChangeQueryResult(
                    title=f"{program.name}",
                    query_suggestion_text=f"{program.name}",
                    icon=self.get_program_icon(program),
                    new_query=f"{base_query}{program.name} ",
                    api=self.api,
                )
            )

        return results

    def get_base_query(self, query: str, prefix: str) -> str:
        """Strip the active autocomplete prefix from the full query string.

        Args:
            query: The full query string.
            prefix: The prefix string being autocompleted.

        Returns:
            The base query string ending with a space separator if non-empty.
        """
        if prefix and query.endswith(prefix):
            # query without autocomplete prefix
            base_query = query[: -len(prefix)]
        else:
            base_query = query

        if base_query and not base_query.endswith(" "):
            base_query += " "

        return base_query

    def autocomplete(
        self, base_query: str, context: AutocompleteContext
    ) -> list[Result]:
        """Generate autocomplete result suggestions based on the parser context.

        Args:
            base_query: The base query prefix string.
            context: The AutocompleteContext containing grammar parsing state.

        Returns:
            A list of Result objects providing autocompletion suggestions.
        """
        result: list[Result] = []

        match context.type:
            case [AutocompleteType.COMMAND, AutocompleteType.TAG]:
                result = [
                    *self.autocomplete_command(base_query, context.prefix),
                    *self.autocomplete_tag(base_query, context.prefix),
                ]
            case [AutocompleteType.TAG]:
                result = self.autocomplete_tag(base_query, context.prefix)
            # case [AutocompleteType.PROGRAM]:
            #     result = self.autocomplete_program(base_query, context.prefix)
            case [AutocompleteType.ADD_TAG_PROGRAM]:
                tag_name = context.args["tag_name"]  # should not fail
                result = self.get_programs_add_tag_action(tag_name, context.prefix)
            case [AutocompleteType.REMOVE_TAG_PROGRAM]:
                tag_name = context.args["tag_name"]  # should not fail
                result = self.get_programs_remove_tag_action(tag_name, context.prefix)
            case _:
                pass

        return result


if __name__ == "__main__":
    try:
        plugin = TagsPlugin()
        plugin.run(setup_default_log_handler=False)
    except Exception as e:
        logger.exception("Unexpected exception: %r", e)
