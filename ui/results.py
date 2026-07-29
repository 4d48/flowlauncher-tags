import logging
from typing import Unpack, override

from flogin import (
    ExecuteResponse,
    Result,
    ResultConstructorKwargs,
)
from flogin.flow.api import FlowLauncherAPI

from config import TAGS_FILE_PATH
from core.programs import Program
from core.tag_manager import TagManager

logger = logging.getLogger(__name__)


class ChangeQueryResult(Result):
    """Result item that updates the Flow Launcher search query upon execution."""

    def __init__(
        self,
        new_query: str,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        """Initialize a ChangeQueryResult instance.

        Args:
            new_query: The new query string to set in Flow Launcher.
            api: The Flow Launcher API instance.
            **kwargs: Additional keyword arguments passed to the Result constructor.
        """
        super().__init__(**kwargs)
        self.new_query: str = new_query
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        """Execute the action to update the Flow Launcher search query.

        Returns:
            An ExecuteResponse specifying UI behavior after execution.
        """
        await self.api.change_query(self.new_query, requery=False)
        return ExecuteResponse(hide=False)


class LaunchProgramResult(Result):
    """Result item that launches a specified program upon execution."""

    def __init__(
        self,
        program: Program,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        """Initialize a LaunchProgramResult instance.

        Args:
            program: The Program instance to be launched.
            api: The Flow Launcher API instance.
            **kwargs: Additional keyword arguments passed to the Result constructor.
        """
        super().__init__(**kwargs)
        self.program: Program = program
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        """Launch the associated program and reset the search query.

        Returns:
            An ExecuteResponse specifying that the launcher UI should hide.
        """
        # if self.program.launch() is None:
        #     await self.api.show_error_message(
        #         "Couldn't launch program", "Program path is not specified"
        #     )

        _ = self.program.launch()

        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)


class AddTagToProgramResult(Result):
    """Result item that attaches a tag to a program upon execution."""

    def __init__(
        self,
        tag: str,
        program: Program,
        tag_manager: TagManager,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        """Initialize an AddTagToProgramResult instance.

        Args:
            tag: The tag name to add.
            program: The target Program instance.
            tag_manager: The TagManager handling tag data persistence.
            api: The Flow Launcher API instance.
            **kwargs: Additional keyword arguments passed to the Result constructor.
        """
        super().__init__(**kwargs)
        self.tag: str = tag
        self.program: Program = program
        self.tag_manager: TagManager = tag_manager
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        """Add the tag to the program, save tags to file, and show a notification.

        Returns:
            An ExecuteResponse specifying that the launcher UI should hide.
        """
        self.tag_manager.add(self.program, self.tag)
        self.tag_manager.to_file(TAGS_FILE_PATH)

        await self.api.show_notification(
            "Success!", f"Added tag '{self.tag}' to program '{self.program.name}'"
        )
        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)

    # @override
    # async def context_menu(self) -> list[Result]:
    #     menu_entries: list[Result] = []

    #     menu_entries.append(title=self.program.path, sub=self.program.icon)

    #     return menu_entries


class RemoveTagFromProgramResult(Result):
    """Result item that removes a tag from a program upon execution."""

    def __init__(
        self,
        tag: str,
        program: Program,
        tag_manager: TagManager,
        api: FlowLauncherAPI,
        **kwargs: Unpack[ResultConstructorKwargs],
    ):
        """Initialize a RemoveTagFromProgramResult instance.

        Args:
            tag: The tag name to remove.
            program: The target Program instance.
            tag_manager: The TagManager handling tag data persistence.
            api: The Flow Launcher API instance.
            **kwargs: Additional keyword arguments passed to the Result constructor.
        """
        super().__init__(**kwargs)
        self.tag: str = tag
        self.program: Program = program
        self.tag_manager: TagManager = tag_manager
        self.api: FlowLauncherAPI = api

    @override
    async def callback(self):
        """Remove the tag from the program, save tags to file, and show a notification.

        Returns:
            An ExecuteResponse specifying that the launcher UI should hide.
        """
        self.tag_manager.remove(self.program, self.tag)
        self.tag_manager.to_file(TAGS_FILE_PATH)

        await self.api.show_notification(
            "Success!", f"Removed tag '{self.tag}' from program '{self.program.name}'"
        )
        await self.api.change_query("", requery=False)

        return ExecuteResponse(hide=True)
