import hashlib
import logging
import shutil
import subprocess
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast, override

from PIL import Image

from core.icon_extractor import (
    get_dll_icon_as_data_uri,
    save_dll_icon_to_png,
)

logger = logging.getLogger(__name__)


class ProgramDict(TypedDict):
    """TypedDict representing serialized program data structure."""

    name: str
    version: str | None
    folder: str | None
    icon: str | None
    path: str


@dataclass(frozen=True)
class Program:
    """Represents an installed program."""

    name: str
    path: str
    version: str | None
    folder: str | None
    icon: str | None

    @property
    def _normalized_path(self) -> str:
        """Return the normalized lower-case resolved file path of the program.

        Returns:
            The normalized path string.
        """
        return str(Path(self.path).resolve()).lower()

    def sha256(self) -> str:
        """Compute SHA-256 hash of the normalized program path.

        Returns:
            The hexadecimal SHA-256 digest string.
        """
        return hashlib.sha256(self._normalized_path.encode()).hexdigest()

    @override
    def __hash__(self) -> int:
        """Return hash value based on the normalized path.

        Returns:
            Hash integer of the normalized path.
        """
        return hash(self._normalized_path)

    @override
    def __eq__(self, other: object) -> bool:
        """Check equality with another object based on normalized path.

        Args:
            other: Object to compare with.

        Returns:
            True if paths match, False if paths differ, or NotImplemented.
        """
        if not isinstance(other, Program):
            return NotImplemented

        return self._normalized_path == other._normalized_path

    def icon_to_file(self, output_path: Path, fallback: Path):
        """
        Extract the program icon and save it as a PNG.
        Uses the fallback icon if an error occurs or if no icon is found.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.icon:
            _ = shutil.copy(fallback, output_path)
            return output_path

        try:
            icon_path, sep, index_str = self.icon.partition(",")
            index = int(index_str) if sep and index_str else 0
            icon_path = icon_path.strip('"')

            if not icon_path or not Path(icon_path).exists():
                _ = shutil.copy(fallback, output_path)
                return output_path

            if icon_path.lower().endswith((".exe", ".dll")):
                save_dll_icon_to_png(icon_path, index, str(output_path), 64)
            else:
                with Image.open(icon_path) as img:
                    img.save(output_path, format="PNG")

            return output_path

        except Exception as e:
            logger.warning(
                "Failed to cache icon for %s (%s): %s", self.name, self.path, e
            )
            _ = shutil.copy(fallback, output_path)
            return output_path

    # dead code probably
    def icon_to_data_uri(self, fallback: str = "") -> str:
        """Convert the program icon to a Data URI string.

        Args:
            fallback: Fallback string to return if icon extraction fails.

        Returns:
            Base64 encoded Data URI string or fallback.
        """
        data_uri = fallback

        if self.icon:
            parts = self.icon.split(",")

            try:
                data_uri = get_dll_icon_as_data_uri(
                    dll_path=parts[0],
                    icon_index=int(parts[1]) if len(parts) > 1 else 0,
                )
            except Exception:
                try:
                    data_uri = get_dll_icon_as_data_uri(dll_path=parts[0], icon_index=0)
                except Exception:
                    pass

        return data_uri

    def launch(self):
        """Launch the program as a subprocess.

        Returns:
            A subprocess.Popen instance representing the running process.
        """
        return subprocess.Popen(self.path)


@dataclass
class ProgramBuilder:
    """Builder helper class for constructing Program instances."""

    name: str
    version: str | None = None
    folder: str | None = None
    icon: str | None = None
    path: str | None = None

    def build(self) -> Program:
        """Build and return a Program instance from current builder attributes.

        Returns:
            A new Program instance.
        """
        return Program(self.name, self.path or "", self.version, self.folder, self.icon)


def read_registry_entry(key: winreg.HKEYType, name: str) -> str:
    """Safely retrieve a string from the registry, satisfying the linter.

    Args:
        key: Open registry key handle.
        name: Value name to read.

    Returns:
        The string value from the registry.

    Raises:
        ValueError: If the registry value type is not a string type.
    """
    value, reg_type = cast(tuple[str, int], winreg.QueryValueEx(key, name))

    # Check if the type is one of the allowed string types
    if reg_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise ValueError(f"Unexpected registry value type: {reg_type} for '{name}'")

    return value


def read_programs_from_registry_path(
    hive: int, subkey_path: str
) -> list[ProgramBuilder]:
    """Read installed programs from a specific registry key path.

    Args:
        hive: Registry hive handle (e.g., winreg.HKEY_LOCAL_MACHINE).
        subkey_path: Path string to the registry subkey.

    Returns:
        A list of ProgramBuilder instances extracted from the registry path.
    """
    programs: list[ProgramBuilder] = []
    try:
        # Open the registry key for reading
        with winreg.OpenKey(hive, subkey_path) as key:
            # Get the number of subkeys (folders) in this key
            num_subkeys = winreg.QueryInfoKey(key)[0]

            for i in range(num_subkeys):
                try:
                    # Get the subkey name (e.g., GUID or program name)
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        # Try to get the DisplayName value
                        try:
                            name: str = read_registry_entry(subkey, "DisplayName")
                        except (OSError, ValueError):
                            continue  # Skip if there is no display name

                        try:
                            version: str | None = read_registry_entry(
                                subkey, "DisplayVersion"
                            )
                        except (OSError, ValueError):
                            version = None

                        try:
                            folder: str | None = read_registry_entry(
                                subkey, "InstallLocation"
                            )
                        except (OSError, ValueError):
                            folder = None

                        try:
                            icon: str | None = read_registry_entry(
                                subkey, "DisplayIcon"
                            )
                        except (OSError, ValueError):
                            icon = None

                        programs.append(
                            ProgramBuilder(
                                icon=icon,
                                name=name,
                                version=version,
                                folder=folder,
                            )
                        )
                except OSError:
                    continue
    except OSError:
        # If the key does not exist or access is denied, return an empty list
        pass

    return programs


def get_programs_from_registry() -> list[ProgramBuilder]:
    """Collect programs from all required registry paths (x64, x32, Current User).

    Returns:
        A list of unique ProgramBuilder instances sorted by program name.
    """
    registry_paths = [
        # x64 programs for all users
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        # x32 programs for all users (on 64-bit OS)
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        # Programs for current user
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    ]

    unique_programs: dict[tuple[str, str | None, str | None], ProgramBuilder] = {}

    # Deduplication
    for hive, path in registry_paths:
        for program in read_programs_from_registry_path(hive, path):
            dedup_key = (program.name, program.version or None, program.folder or None)

            if dedup_key not in unique_programs:
                unique_programs[dedup_key] = program

    programs: list[ProgramBuilder] = sorted(
        unique_programs.values(), key=lambda x: x.name.lower()
    )

    return programs


def get_all_installed_programs() -> list[Program]:
    """Retrieve all installed programs detected from the Windows registry.

    Returns:
        A list of constructed Program instances.
    """
    program_drafts = get_programs_from_registry()

    for program in program_drafts:
        if program.icon and "exe" in program.icon.lower():
            program.path = program.icon.split(",", 1)[0].strip('"')

    programs = [program.build() for program in program_drafts if program.path]

    return programs


if __name__ == "__main__":
    print("Gathering information from the registry...\n")
    installed_programs = get_all_installed_programs()

    print(f"Total unique programs found: {len(installed_programs)}")
    print("-" * 60)

    for idx, prog in enumerate(installed_programs, 1):
        print(f"{idx}. {prog.name}")
        print(f"   Version: {prog.version}")
        print(f"   Install directory: {prog.folder}")
        print(f"   Icon: {prog.icon}")
        print(f"   Path: {prog.path}")
        print("-" * 60)
