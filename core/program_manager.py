import difflib
import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Self

from core.programs import Program, ProgramDict, get_all_installed_programs


class ProgramManager:
    """Manages loading, saving, and retrieving installed programs."""

    def __init__(self, programs: list[Program] | None = None):
        self._programs: list[Program] = programs if programs is not None else []

    @property
    def programs(self) -> list[Program]:
        """
        Get a shallow copy of the loaded programs.

        Returns:
            A new list containing the Program instances to prevent accidental
            modification of the manager's internal state.
        """
        return self._programs.copy()

    @classmethod
    def from_os(cls) -> Self:
        """
        Scan the Windows Registry to load all installed programs.

        Returns:
            An instance of ProgramManager populated with programs detected in the OS.
        """
        programs: list[Program] = get_all_installed_programs()

        return cls(programs)

    @classmethod
    def from_file(cls, path: Path) -> Self:
        """
        Load programs from a structured JSON file.

        Args:
            filename: The Path to the JSON file.

        Returns:
            An instance of ProgramManager populated with data from the file.

        Raises:
            FileNotFoundError: If the specified file does not exist.
            json.JSONDecodeError: If the file contains invalid JSON data.
            TypeError/KeyError: If the JSON structure does not match Program fields.
        """
        with open(path, encoding="utf-8") as f:
            data: list[ProgramDict] = json.load(f)  # pyright: ignore[reportAny]

            programs: list[Program] = [Program(**program_data) for program_data in data]

        return cls(programs)

    def to_file(self, path: Path) -> None:
        """
        Save the current list of programs to a JSON file.

        Args:
            filename: The destination file Path.

        Raises:
            OSError: If the file cannot be written (e.g., due to permission errors).
        """
        program_data = [asdict(program) for program in self._programs]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(program_data, f)

    def find_one(
        self, name: str, programs: Iterable[Program] | None = None
    ) -> Program | None:
        """
        Find program that exactly matches the given criteria.

        Args:
            name: The name of the program to find.
            programs: An Iterable in which search is performed.

        Returns:
            A first Program object that exactly matches the criteria or None if no match is found.

        If `programs` set to `None`, search is performed over internal state.
        """
        if not programs:
            programs = self._programs

        for program in programs:
            if program.name == name:
                return program

        return None

    def find(
        self, name: str, programs: Iterable[Program] | None = None
    ) -> set[Program]:
        """
        Find programs that match the given criteria.
        Prioritizes substring matches, falls back to fuzzy search for typos.

        Args:
            name: The name of the program to find.
            programs: An Iterable in which search is performed.

        Returns:
            A set of Program objects that match the criteria.

        If `programs` set to `None`, search is performed over internal state.
        """
        if not name:
            return set(self._programs)

        if not programs:
            programs = self._programs

        matches: dict[str, Program] = {
            program.name: program
            for program in programs
            if name in program.name.lower()
        }

        program_dict = {program.name: program for program in programs}

        fuzzy_matches: list[str] = difflib.get_close_matches(
            name, program_dict.keys(), n=10, cutoff=0.4
        )

        for prog_name in fuzzy_matches:
            matches[prog_name] = program_dict[prog_name]

        return set(matches.values())
