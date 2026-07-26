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
    name: str
    version: str | None
    folder: str | None
    icon: str | None
    path: str


@dataclass(frozen=True)
class Program:
    name: str
    path: str
    version: str | None
    folder: str | None
    icon: str | None

    @property
    def _normalized_path(self) -> str:
        return str(Path(self.path).resolve()).lower()

    def sha256(self) -> str:
        return hashlib.sha256(self._normalized_path.encode()).hexdigest()

    @override
    def __hash__(self) -> int:
        return hash(self._normalized_path)

    @override
    def __eq__(self, other: object) -> bool:
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
        return subprocess.Popen(self.path)


@dataclass
class ProgramBuilder:
    name: str
    version: str | None = None
    folder: str | None = None
    icon: str | None = None
    path: str | None = None

    def build(self) -> Program:
        return Program(self.name, self.path or "", self.version, self.folder, self.icon)


def read_registry_entry(key: winreg.HKEYType, name: str) -> str:
    """Безпечно отримує рядок з реєстру, задовольняючи лінтер."""
    value, reg_type = cast(tuple[str, int], winreg.QueryValueEx(key, name))

    # Перевіряємо, чи є тип одним із дозволених рядкових типів
    if reg_type not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        raise ValueError(f"Unexpected registry value type: {reg_type} for '{name}'")

    return value


def read_programs_from_registry_path(
    hive: int, subkey_path: str
) -> list[ProgramBuilder]:
    """
    Зчитує програми з конкретної гілки реєстру.
    """
    programs: list[ProgramBuilder] = []
    try:
        # Відкриваємо гілку реєстру для читання
        with winreg.OpenKey(hive, subkey_path) as key:
            # Отримуємо кількість підключів (папок) у цій гілці
            num_subkeys = winreg.QueryInfoKey(key)[0]

            for i in range(num_subkeys):
                try:
                    # Отримуємо ім'я підключа (наприклад, GUID або назву програми)
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        # Намагаємося отримати параметр DisplayName
                        try:
                            name: str = read_registry_entry(subkey, "DisplayName")
                        except (OSError, ValueError):
                            continue  # Пропускаємо, якщо немає назви

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
        # Якщо гілка не існує або немає доступу, просто повертаємо порожній список
        pass

    return programs


def get_programs_from_registry() -> list[ProgramBuilder]:
    """
    Збирає програми з усіх необхідних гілок реєстру (x64, x32, Current User).
    """
    registry_paths = [
        # x64 програми для всіх користувачів
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        # x32 програми для всіх користувачів (на 64-бітній ОС)
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        # Програми для поточного користувача
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
    program_drafts = get_programs_from_registry()

    for program in program_drafts:
        if program.icon and "exe" in program.icon.lower():
            program.path = program.icon.split(",", 1)[0].strip('"')

    programs = [program.build() for program in program_drafts if program.path]

    return programs


if __name__ == "__main__":
    print("Збираю інформацію з реєстру...\n")
    installed_programs = get_all_installed_programs()

    print(f"Загалом знайдено унікальних програм: {len(installed_programs)}")
    print("-" * 60)

    for idx, prog in enumerate(installed_programs, 1):
        print(f"{idx}. {prog.name}")
        print(f"   Версія: {prog.version}")
        print(f"   Папка установки: {prog.folder}")
        print(f"   Іконка: {prog.icon}")
        print(f"   Шлях: {prog.path}")
        print("-" * 60)
