import difflib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Self

from core.programs import Program


class TagManager:
    """Manages tags associated with programs."""

    def __init__(self, tag_to_programs: dict[str, set[Program]] | None = None):
        """Initialize a TagManager instance.

        Args:
            tag_to_programs: Optional initial mapping of tag names to sets of Program instances.
        """
        self._tag_to_programs: dict[str, set[Program]] = (
            tag_to_programs if tag_to_programs is not None else {}
        )

    @property
    def tags(self) -> set[str]:
        """Return the set of all existing tag names.

        Returns:
            A set of tag name strings.
        """
        return set(self._tag_to_programs.keys())

    def add(self, program: Program, tag: str):
        """Associate a program with a specified tag.

        Args:
            program: The Program instance to tag.
            tag: The tag name to add.
        """
        if tag not in self._tag_to_programs:
            self._tag_to_programs[tag] = set()

        self._tag_to_programs[tag].add(program)

    def remove(self, program: Program, tag: str):
        """Remove a tag association from a program.

        Args:
            program: The Program instance.
            tag: The tag name to remove.
        """
        if tag not in self._tag_to_programs:
            return

        self._tag_to_programs[tag].discard(program)

        if not self._tag_to_programs[tag]:
            _ = self._tag_to_programs.pop(tag, None)

    def search_by_tag(self, tag: str) -> set[Program]:
        """Retrieve all programs associated with a given tag.

        Args:
            tag: The tag name to search for.

        Returns:
            A set of Program instances matching the tag.
        """
        return self._tag_to_programs.get(tag, set())

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """Load TagManager state from a JSON file.

        Args:
            path: The Path to the JSON file.

        Returns:
            An instance of TagManager populated with data from the file.
        """
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        tag_to_programs = {
            tag: {Program(**prog_dict) for prog_dict in programs_list}
            for tag, programs_list in raw_data.items()
        }

        return cls(tag_to_programs)

    def to_file(self, path: Path) -> None:
        """Save TagManager state to a JSON file.

        Args:
            path: The destination file Path.
        """
        serializable_dict = {
            tag: [asdict(program) for program in programs_list]
            for tag, programs_list in self._tag_to_programs.items()
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable_dict, f, ensure_ascii=False, indent=4)

    def find(self, name: str) -> list[str]:
        """
        Find tags that match the given criteria. Fuzzy search.

        Args:
            name: The name of the tag to find.

        Returns:
            A list of tags that match the criteria.
        """
        matches: list[str] = difflib.get_close_matches(
            name, self._tag_to_programs.keys(), n=10, cutoff=0.5
        )

        return matches
