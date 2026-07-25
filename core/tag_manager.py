import difflib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Self

from core.programs import Program


class TagManager:
    def __init__(self, tag_to_programs: dict[str, list[Program]] | None = None):
        self._tag_to_programs: dict[str, list[Program]] = (
            tag_to_programs if tag_to_programs is not None else {}
        )
        # self._program_to_tags: dict[Program, list[str]] = {}

    @property
    def tags(self) -> set[str]:
        return set(self._tag_to_programs.keys())

    def add(self, program: Program, tag: str):
        if tag not in self._tag_to_programs:
            self._tag_to_programs[tag] = []

        self._tag_to_programs[tag].append(program)

        # if program not in self._program_to_tags:
        #     self._program_to_tags[program] = []

        # self._program_to_tags[program].append(tag)

    def remove(self, program: Program, tag: str):
        if tag in self._tag_to_programs and program in self._tag_to_programs[tag]:
            self._tag_to_programs[tag].remove(program)

    def search_by_tag(self, tag: str) -> list[Program]:
        return self._tag_to_programs.get(tag, [])

    @classmethod
    def from_file(cls, path: Path) -> Self:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        tag_to_programs = {
            tag: [Program(**prog_dict) for prog_dict in programs_list]
            for tag, programs_list in raw_data.items()
        }

        return cls(tag_to_programs)

    def to_file(self, path: Path) -> None:
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

        return [tag for tag in matches]
