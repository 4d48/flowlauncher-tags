import sys
from pathlib import Path

plugindir = Path.absolute(Path(__file__).parent)
sys.path.insert(0, str(plugindir / ".venv" / "Lib" / "site-packages"))

import logging
import os
from collections.abc import Iterable
from typing import Unpack, override

from flogin import (
    ExecuteResponse,
    Plugin,
    Query,
    Result,
    ResultConstructorKwargs,
)
from flogin.flow.api import FlowLauncherAPI

from core.lexer import CommandKeyword, Lexer
from core.parser import (
    AddTag,
    AutocompleteContext,
    AutocompleteType,
    GetProgramsByTag,
    Parser,
    ParserError,
    RemoveTag,
)
from core.program_manager import ProgramManager
from core.programs import Program
from core.tag_manager import TagManager

appdata = os.environ.get("APPDATA")

PLUGIN_KEYWORD = "tag"
PLUGIN_DATADIR = (
    (Path(appdata) / "FlowLauncher" / "Cache" / "Plugins" / "Tags")
    if appdata
    else Path(".")
)

PLUGIN_DATADIR.mkdir(parents=True, exist_ok=True)

TAGS_FILE_PATH = PLUGIN_DATADIR / "tags.json"
PROGRAMS_FILE_PATH = PLUGIN_DATADIR / "programs.json"

ICON_MISSING_PATH = Path("Images") / "icon_missing.png"

logging.basicConfig(
    filename=PLUGIN_DATADIR / "plugin.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


class ChangeQueryResult(Result):
    def __init__(
        self,
        new_query: str,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        super().__init__(**kwargs)
        self.new_query: str = new_query
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        await self.api.change_query(self.new_query, requery=False)
        return ExecuteResponse(hide=False)


class LaunchProgramResult(Result):
    def __init__(
        self,
        program: Program,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        super().__init__(**kwargs)
        self.program: Program = program
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        if self.program.launch() is None:
            await self.api.show_error_message(
                "Couldn't launch program", "Program path is not specified"
            )

        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)


class AddTagToProgramResult(Result):
    def __init__(
        self,
        tag: str,
        program: Program,
        tag_manager: TagManager,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        super().__init__(**kwargs)
        self.tag: str = tag
        self.program: Program = program
        self.tag_manager: TagManager = tag_manager
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        self.tag_manager.add(self.program, self.tag)
        self.tag_manager.to_file(TAGS_FILE_PATH)

        await self.api.show_notification(
            "Success!", f"Added tag '{self.tag}' to program '{self.program.name}'"
        )
        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)


class RemoveTagFromProgramResult(Result):
    def __init__(
        self,
        tag: str,
        program: Program,
        tag_manager: TagManager,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        super().__init__(**kwargs)
        self.tag: str = tag
        self.program: Program = program
        self.tag_manager: TagManager = tag_manager
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        self.tag_manager.remove(self.program, self.tag)
        self.tag_manager.to_file(TAGS_FILE_PATH)

        await self.api.show_notification(
            "Success!", f"Removed tag '{self.tag}' from program '{self.program.name}'"
        )
        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)


# largest score value in FlowLauncher (2^31 - 1)
MAX_SCORE: int = 2_147_483_647


class TagsPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.program_manager: ProgramManager
        self.tag_manager: TagManager

    @Plugin.event  # pyright: ignore[reportUnknownMemberType, reportUntypedFunctionDecorator]
    async def on_initialization(self):
        try:
            self.program_manager = ProgramManager.from_file(PROGRAMS_FILE_PATH)
            logger.info("Loaded programs from file")
        except (
            Exception
        ) as e:  # todo: should differentiate access problems from file unexistence
            logger.exception("Failed to load programs from file: %s", e)
            self.program_manager = ProgramManager.from_os()
            self.program_manager.to_file(PROGRAMS_FILE_PATH)

        try:
            self.tag_manager = TagManager.from_file(TAGS_FILE_PATH)
            logger.info("Loaded tags from file")
        except Exception as e:
            logger.exception("Failed to load tags from file: %s", e)
            self.tag_manager = TagManager()

    @Plugin.search()
    async def search_handler(self, query: Query[None]) -> list[Result]:
        logger.debug("Query: %r", query)

        results: list[Result] = []

        text = query.text

        if query.original_query.endswith(" "):
            text += " "

        lexer = Lexer(text)
        parser = Parser()

        try:
            for token in lexer.tokens:
                parser.parse_token(token)

            parser_result = parser.get_result()
        except ParserError as e:
            logger.exception("Parser error: %s", e)
            return results

        context: AutocompleteContext = parser_result.autocomplete_context
        base_query: str = self.get_base_query(query.original_query, context.prefix)

        if not parser_result.command:
            results.extend(self.autocomplete(base_query, context))
            return results

        match parser_result.command:
            case GetProgramsByTag():
                results.extend(self.autocomplete_tag(base_query, context.prefix))
                results.extend(self.get_programs_by_tag(parser_result.command.tag_name))
            case AddTag() | RemoveTag():
                results.extend(self.autocomplete(base_query, context))
            case _:
                pass

        return results

    def get_programs_by_tag(self, tag: str) -> list[Result]:
        result: list[Result] = []

        for program in self.tag_manager.search_by_tag(tag):
            result.append(
                LaunchProgramResult(
                    title=f"{program.name}",
                    query_suggestion_text=f"{program.name}",
                    icon=program.icon_to_data_uri(str(ICON_MISSING_PATH)),
                    program=program,
                    api=self.api,
                )
            )

        return result

    def get_programs_add_tag_action(self, tag: str, prefix: str) -> list[Result]:
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
                    icon=program.icon_to_data_uri(str(ICON_MISSING_PATH)),
                    tag=tag,
                    program=program,
                    tag_manager=self.tag_manager,
                    api=self.api,
                )
            )

        return results

    def get_programs_remove_tag_action(self, tag: str, prefix: str) -> list[Result]:
        results: list[Result] = []

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
                    icon=program.icon_to_data_uri(str(ICON_MISSING_PATH)),
                    tag=tag,
                    tag_manager=self.tag_manager,
                    program=program,
                    api=self.api,
                )
            )

        return results

    def autocomplete_command(self, base_query: str) -> list[Result]:
        return [
            ChangeQueryResult(
                title="Add tag",
                query_suggestion_text=f"{CommandKeyword.ADD_TAG}",
                icon="Images/transparent.png",
                score=MAX_SCORE,
                new_query=f"{base_query}{CommandKeyword.ADD_TAG} ",
                api=self.api,
            ),
            ChangeQueryResult(
                title="Remove tag",
                query_suggestion_text=f"{CommandKeyword.REMOVE_TAG}",
                icon="Images/transparent.png",
                score=MAX_SCORE,
                new_query=f"{base_query}{CommandKeyword.REMOVE_TAG} ",
                api=self.api,
            ),
        ]

    def autocomplete_tag(self, base_query: str, prefix: str) -> list[Result]:
        results: list[Result] = []

        for tag in self.tag_manager.tags:
            if tag != prefix and tag.startswith(prefix):
                results.append(
                    ChangeQueryResult(
                        title=f"{tag}",
                        query_suggestion_text=f"{tag}",
                        icon="Images/transparent.png",
                        new_query=f"{base_query}{tag} ",
                        api=self.api,
                    )
                )

        return results

    def autocomplete_program(self, base_query: str, prefix: str) -> list[Result]:
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
                    icon=program.icon_to_data_uri(str(ICON_MISSING_PATH)),
                    new_query=f"{base_query}{program.name} ",
                    api=self.api,
                )
            )

        return results

    def get_base_query(self, query: str, prefix: str) -> str:
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
        result: list[Result] = []

        match context.type:
            case [AutocompleteType.COMMAND, AutocompleteType.TAG]:
                result = [
                    *self.autocomplete_command(base_query),
                    *self.autocomplete_tag(base_query, context.prefix),
                ]
            case [AutocompleteType.TAG]:
                result = self.autocomplete_tag(base_query, context.prefix)
            case [AutocompleteType.PROGRAM]:
                # result = self.autocomplete_program(base_query, context.prefix)
                result = []
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
