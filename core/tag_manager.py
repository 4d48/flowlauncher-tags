import difflib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Self

from core.programs import Program


class TagManager:
    def __init__(self, tag_to_programs: dict[str, set[Program]] | None = None):
        self._tag_to_programs: dict[str, set[Program]] = (
            tag_to_programs if tag_to_programs is not None else {}
        )

    @property
    def tags(self) -> set[str]:
        return set(self._tag_to_programs.keys())

    def add(self, program: Program, tag: str):
        if tag not in self._tag_to_programs:
            self._tag_to_programs[tag] = set()

        self._tag_to_programs[tag].add(program)

    def remove(self, program: Program, tag: str):
        if tag not in self._tag_to_programs:
            return

        self._tag_to_programs[tag].discard(program)

        if not self._tag_to_programs[tag]:
            _ = self._tag_to_programs.pop(tag, None)

    def search_by_tag(self, tag: str) -> set[Program]:
        return self._tag_to_programs.get(tag, set())

    @classmethod
    def from_file(cls, path: Path) -> Self:
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        tag_to_programs = {
            tag: {Program(**prog_dict) for prog_dict in programs_list}
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

        return matches
