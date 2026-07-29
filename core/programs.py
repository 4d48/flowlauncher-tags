# Mostly AI generated

import ctypes
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import uuid
import winreg
from ctypes import (
    HRESULT,
    POINTER,
    Structure,
    byref,
    c_int,
    c_ulong,
    c_void_p,
    c_wchar_p,
)
from ctypes.wintypes import DWORD, MAX_PATH
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, cast, override

from PIL import Image

from core.icon_extractor import save_dll_icon_to_png

logger = logging.getLogger(__name__)

UNINSTALL_KEYWORDS: set[str] = {
    "uninstall",
    "unins000",
    "unins001",
    "remove",
    "deinstall",
    "setup",
    "msiexec",
}


class GUID(Structure):
    """Represent a Windows GUID structure for COM interface interactions."""

    _fields_ = [
        ("Data1", DWORD),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __init__(self, guid_str: str) -> None:
        """Initialize GUID structure from a string representation.

        Args:
            guid_str: String GUID in standard bracketed format.
        """
        super().__init__()
        u = uuid.UUID(guid_str)
        self.Data1 = u.time_low
        self.Data2 = u.time_mid
        self.Data3 = u.time_hi_version
        for i, b in enumerate(u.bytes[8:]):
            self.Data4[i] = b


CLSID_ShellLink = GUID("{00021401-0000-0000-C000-000000000046}")
IID_IShellLinkW = GUID("{000214F9-0000-0000-C000-000000000046}")
IID_IPersistFile = GUID("{0000010b-0000-0000-C000-000000000046}")


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
        return get_canonical_path(self.path)

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

    def icon_to_file(self, output_path: Path, fallback: Path) -> Path:
        """Extract the program icon and save it as a PNG file.

        Uses the fallback icon if an error occurs or if no icon is found.

        Args:
            output_path: Path where the extracted icon PNG should be saved.
            fallback: Path to the fallback icon file.

        Returns:
            Path to the saved icon image file.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.icon:
            logger.debug("No icon defined for %s, using fallback", self.name)
            _ = shutil.copy(fallback, output_path)
            return output_path

        try:
            icon_path, sep, index_str = self.icon.partition(",")
            index = int(index_str) if sep and index_str else 0
            icon_path = icon_path.strip('"')

            if not icon_path or not Path(icon_path).exists():
                logger.debug(
                    "Icon path does not exist for %s (%s), using fallback",
                    self.name,
                    icon_path,
                )
                _ = shutil.copy(fallback, output_path)
                return output_path

            if icon_path.lower().endswith((".exe", ".dll", ".icl", ".cpl", ".mun")):
                save_dll_icon_to_png(icon_path, index, str(output_path), 64)
            else:
                with Image.open(icon_path) as img:
                    img.save(output_path, format="PNG")

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise ValueError("Extracted icon file is missing or 0 bytes")

            with Image.open(output_path) as test_img:
                test_img.verify()

            return output_path

        except Exception as e:
            logger.warning(
                "Failed to cache icon for %s (%s): %s", self.name, self.path, e
            )
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            _ = shutil.copy(fallback, output_path)
            return output_path

    def launch(self) -> subprocess.Popen[bytes]:
        """Launch the program as a subprocess.

        Returns:
            A subprocess.Popen instance representing the running process.
        """
        return subprocess.Popen(self.path)


@dataclass
class ProgramBuilder:
    """Construct Program instances from multiple indexing sources."""

    path: str
    name: str | None = None
    version: str | None = None
    folder: str | None = None
    icon: str | None = None
    _has_start_menu_name: bool = field(default=False, repr=False)
    _has_start_menu_folder: bool = field(default=False, repr=False)
    _has_start_menu_icon: bool = field(default=False, repr=False)

    def merge_from_registry(
        self,
        name: str | None,
        version: str | None,
        folder: str | None,
        icon: str | None,
    ) -> None:
        """Merge program metadata originating from the Windows registry.

        Args:
            name: Display name from registry.
            version: Display version from registry.
            folder: Install location from registry.
            icon: Display icon from registry.
        """
        if not self._has_start_menu_name and name and not self.name:
            self.name = name
        if version and not self.version:
            self.version = version
        if not self._has_start_menu_folder and folder and not self.folder:
            self.folder = folder
        if (
            not self._has_start_menu_icon
            and icon
            and not is_installer_or_stub(icon)
            and not self.icon
        ):
            self.icon = icon

    def merge_from_start_menu(
        self,
        name: str | None,
        folder: str | None,
        icon: str | None,
    ) -> None:
        """Merge program metadata originating from a Start Menu shortcut.

        Args:
            name: Title of the shortcut.
            folder: Working directory of the shortcut.
            icon: Custom icon location specified by the shortcut.
        """
        if name:
            self.name = name
            self._has_start_menu_name = True
        if folder:
            self.folder = folder
            self._has_start_menu_folder = True
        if icon and not is_installer_or_stub(icon):
            self.icon = icon
            self._has_start_menu_icon = True

    def build(self) -> Program:
        """Build and return a Program instance from current builder attributes.

        Returns:
            A new Program instance.
        """
        final_name = self.name or Path(self.path).stem
        final_folder = self.folder or str(Path(self.path).parent)
        final_icon = (
            self.icon
            if (self.icon and not is_installer_or_stub(self.icon))
            else self.path
        )
        return Program(
            name=final_name,
            path=self.path,
            version=self.version,
            folder=final_folder,
            icon=final_icon,
        )


def get_canonical_path(path_str: str) -> str:
    """Return the normalized lowercase resolved file path for deduplication.

    Args:
        path_str: Raw path string to normalize.

    Returns:
        Canonical resolved path string in lowercase.
    """
    cleaned = path_str.partition(",")[0].strip('"').strip()
    try:
        return str(Path(cleaned).resolve()).lower()
    except Exception:
        return cleaned.lower()


def is_installer_or_stub(path_str: str) -> bool:
    """Check if a path points to Windows Installer cache or an installer/uninstaller stub.

    Args:
        path_str: File path string to evaluate.

    Returns:
        True if the path is inside an installer cache or points to a stub executable, False otherwise.
    """
    path_lower = path_str.lower()
    if "\\windows\\installer\\" in path_lower or "/windows/installer/" in path_lower:
        return True
    if "msiexec.exe" in path_lower:
        return True
    return False


def is_uninstaller(name: str, target_path: str) -> bool:
    """Check whether a shortcut or program target represents an uninstaller or setup executable.

    Args:
        name: Program or shortcut display name.
        target_path: File path to the executable.

    Returns:
        True if the item appears to be an uninstaller or setup program, False otherwise.
    """
    name_lower = name.lower()
    path_lower = target_path.lower()
    stem_lower = Path(target_path).stem.lower()

    if is_installer_or_stub(target_path):
        return True

    for kw in UNINSTALL_KEYWORDS:
        if kw in name_lower or kw in stem_lower:
            return True
        if f"\\{kw}" in path_lower or f"/{kw}" in path_lower:
            return True

    return False


MSI_ALIAS_MAP: dict[str, str] = {
    "digitals": "selfcert",
    "vba": "selfcert",
    "cert": "selfcert",
    "certificate": "selfcert",
    "сертифікат": "selfcert",
    "setlanguage": "setlang",
    "language": "setlang",
    "мовні": "setlang",
    "wxp": "msouc",
    "ois": "ois",
    "picture": "ois",
}


def resolve_msi_shortcut(
    shortcut_path: str, initial_target: str | None = None
) -> str | None:
    """Resolve an MSI Advertised shortcut (.lnk) to its target executable path.

    Args:
        shortcut_path: Absolute path string to the .lnk file.
        initial_target: Optional initial target path retrieved from IShellLink.

    Returns:
        Target executable path if resolved, None otherwise.
    """
    msi = getattr(ctypes.windll, "msi", None)
    if msi is None:
        logger.debug("[MSI API] msi.dll is unavailable")
        return None

    sz_product_code = ctypes.create_unicode_buffer(39)
    sz_feature_id = ctypes.create_unicode_buffer(39)
    sz_component_code = ctypes.create_unicode_buffer(39)

    res = msi.MsiGetShortcutTargetW(
        shortcut_path,
        sz_product_code,
        sz_feature_id,
        sz_component_code,
    )
    if res != 0:
        logger.debug(
            "[MSI API] MsiGetShortcutTargetW returned %d for %s", res, shortcut_path
        )
        return None

    pcode = sz_product_code.value
    fcode = sz_feature_id.value
    ccode = sz_component_code.value

    logger.debug(
        "[MSI API] Shortcut target codes for %s: Product=%s, Feature=%s, Component=%s",
        Path(shortcut_path).name,
        pcode,
        fcode,
        ccode,
    )

    # 1. Try resolving via Component Code if available
    if ccode:
        buf_size = DWORD(MAX_PATH)
        path_buf = ctypes.create_unicode_buffer(MAX_PATH)
        state = msi.MsiGetComponentPathW(
            pcode,
            ccode,
            path_buf,
            byref(buf_size),
        )
        logger.debug(
            "[MSI API] MsiGetComponentPathW state=%d, path=%s", state, path_buf.value
        )

        if state in (1, 3, 4, 5) and path_buf.value:
            target = os.path.expandvars(path_buf.value.strip())
            if (
                target
                and target.lower().endswith(".exe")
                and Path(target).exists()
                and not is_installer_or_stub(target)
            ):
                logger.debug("[MSI API] Successfully resolved target: %s", target)
                return target

    # 2. Fallback: discover target executable from Product InstallLocation
    buf_size = DWORD(MAX_PATH)
    path_buf = ctypes.create_unicode_buffer(MAX_PATH)
    res_info = msi.MsiGetProductInfoW(
        pcode, "InstallLocation", path_buf, byref(buf_size)
    )
    install_loc = path_buf.value.strip() if res_info == 0 else ""

    if not install_loc:
        reg_paths = [
            (
                winreg.HKEY_LOCAL_MACHINE,
                rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{pcode}",
            ),
            (
                winreg.HKEY_LOCAL_MACHINE,
                rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{pcode}",
            ),
            (
                winreg.HKEY_CURRENT_USER,
                rf"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{pcode}",
            ),
        ]
        for hive, subkey in reg_paths:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "InstallLocation")
                    if val and isinstance(val, str):
                        install_loc = val.strip()
                        break
            except OSError:
                pass

    if not install_loc or not Path(install_loc).exists():
        logger.debug("[MSI API] Could not find install location for product %s", pcode)
        return None

    install_path = Path(install_loc)
    shortcut_name = Path(shortcut_path).stem
    candidates: list[Path] = []
    try:
        for p in install_path.rglob("*.exe"):
            if (
                p.is_file()
                and not is_installer_or_stub(str(p))
                and not is_uninstaller(shortcut_name, str(p))
            ):
                if p.stem.lower() not in (
                    "misc",
                    "installer",
                    "setup",
                    "unins000",
                    "unins001",
                ):
                    candidates.append(p)
    except Exception as e:
        logger.debug("[MSI API] Error scanning candidates in %s: %s", install_path, e)

    if not candidates:
        return None

    name_lower = shortcut_name.lower()
    feat_lower = fcode.lower()
    initial_stem = Path(initial_target).stem.lower() if initial_target else ""

    # Priority 1: Known alias mapping
    for key, expected_stem in MSI_ALIAS_MAP.items():
        if key in feat_lower or key in name_lower or key in initial_stem:
            for cand in candidates:
                if cand.stem.lower() == expected_stem:
                    logger.debug(
                        "[MSI API] Resolved target via alias '%s': %s", key, cand
                    )
                    return str(cand)

    # Priority 2: Executive stem in feature_id or initial_stem
    generic_stems = {"misc", "icon", "icons", "pic", "image", "helper"}
    for cand in candidates:
        c_stem = cand.stem.lower()
        if c_stem not in generic_stems and len(c_stem) >= 3:
            if c_stem in feat_lower or (initial_stem and c_stem in initial_stem):
                logger.debug(
                    "[MSI API] Resolved target via stem '%s': %s", c_stem, cand
                )
                return str(cand)

    # Priority 3: Executive stem in shortcut name
    norm_name = name_lower.replace(" ", "")
    for cand in candidates:
        c_stem = cand.stem.lower()
        if c_stem not in generic_stems and len(c_stem) >= 3:
            if c_stem in norm_name:
                logger.debug(
                    "[MSI API] Resolved target via name '%s': %s", c_stem, cand
                )
                return str(cand)

    # Priority 4: Single candidate
    if len(candidates) == 1:
        logger.debug("[MSI API] Resolved single candidate: %s", candidates[0])
        return str(candidates[0])

    return None


def resolve_shortcut(shortcut_path: str) -> tuple[str | None, str | None, str | None]:
    """Resolve a Windows shortcut (.lnk file) to obtain target path, working directory, and icon location.

    Args:
        shortcut_path: Absolute path string to the .lnk file.

    Returns:
        Tuple containing (target_path, working_dir, icon_location).
    """
    logger.debug("Resolving shortcut: %s", shortcut_path)
    ole32 = getattr(ctypes.windll, "ole32", None)
    if ole32 is None:
        logger.debug("ole32.dll unavailable")
        return None, None, None

    need_uninit = False
    try:
        co_init_hr = ole32.CoInitialize(None)
        if co_init_hr in (0, 1):
            need_uninit = True

        shell_link_ptr = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(CLSID_ShellLink),
            None,
            1,  # CLSCTX_INPROC_SERVER
            byref(IID_IShellLinkW),
            byref(shell_link_ptr),
        )
        if hr != 0 or not shell_link_ptr:
            logger.debug("CoCreateInstance IShellLinkW failed hr=%d", hr)
            return None, None, None

        persist_file_ptr = c_void_p()
        vtable_shell_link = ctypes.cast(
            shell_link_ptr, POINTER(POINTER(c_void_p))
        ).contents

        # QueryInterface: VTable index 0
        query_interface_fn = ctypes.WINFUNCTYPE(
            HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p)
        )(vtable_shell_link[0])

        hr = query_interface_fn(
            shell_link_ptr, byref(IID_IPersistFile), byref(persist_file_ptr)
        )
        if hr != 0 or not persist_file_ptr:
            logger.debug("QueryInterface IPersistFile failed hr=%d", hr)
            release_fn = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtable_shell_link[2])
            release_fn(shell_link_ptr)
            return None, None, None

        vtable_persist_file = ctypes.cast(
            persist_file_ptr, POINTER(POINTER(c_void_p))
        ).contents

        # Load: VTable index 5 (must include c_void_p for the 'this' pointer)
        load_fn = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p, DWORD)(
            vtable_persist_file[5]
        )
        hr = load_fn(persist_file_ptr, shortcut_path, 0)  # STGM_READ = 0

        target_path: str | None = None
        working_dir: str | None = None
        icon_location: str | None = None

        if hr == 0:
            # GetPath: VTable index 3 (SLGP_UNCPRIORITY = 0x2)
            path_buf = ctypes.create_unicode_buffer(MAX_PATH)
            get_path_fn = ctypes.WINFUNCTYPE(
                HRESULT, c_void_p, c_wchar_p, c_int, c_void_p, DWORD
            )(vtable_shell_link[3])
            if get_path_fn(shell_link_ptr, path_buf, MAX_PATH, None, 0x2) == 0:
                val = os.path.expandvars(path_buf.value.strip())
                if val:
                    target_path = val

            # GetWorkingDirectory: VTable index 8
            work_buf = ctypes.create_unicode_buffer(MAX_PATH)
            get_work_dir_fn = ctypes.WINFUNCTYPE(HRESULT, c_void_p, c_wchar_p, c_int)(
                vtable_shell_link[8]
            )
            if get_work_dir_fn(shell_link_ptr, work_buf, MAX_PATH) == 0:
                val = os.path.expandvars(work_buf.value.strip())
                if val:
                    working_dir = val

            # GetIconLocation: VTable index 16
            icon_buf = ctypes.create_unicode_buffer(MAX_PATH)
            icon_index = c_int(0)
            get_icon_fn = ctypes.WINFUNCTYPE(
                HRESULT, c_void_p, c_wchar_p, c_int, POINTER(c_int)
            )(vtable_shell_link[16])
            if get_icon_fn(shell_link_ptr, icon_buf, MAX_PATH, byref(icon_index)) == 0:
                val = os.path.expandvars(icon_buf.value.strip())
                if val and Path(val).exists():
                    icon_location = f"{val},{icon_index.value}"
        else:
            logger.debug("IPersistFile::Load failed hr=%d for %s", hr, shortcut_path)

        # Release COM interface pointers
        release_persist_fn = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(
            vtable_persist_file[2]
        )
        release_persist_fn(persist_file_ptr)

        release_shell_fn = ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtable_shell_link[2])
        release_shell_fn(shell_link_ptr)

        logger.debug(
            "IShellLink result for %s: target=%s, workdir=%s, icon=%s",
            Path(shortcut_path).name,
            target_path,
            working_dir,
            icon_location,
        )

        # Fallback to MSI API for Advertised Shortcuts if IShellLink targets an installer stub or fails
        if (
            not target_path
            or is_installer_or_stub(target_path)
            or not Path(target_path).exists()
        ):
            logger.debug(
                "Triggering MSI fallback resolution for shortcut %s",
                Path(shortcut_path).name,
            )
            msi_target = resolve_msi_shortcut(shortcut_path, initial_target=target_path)
            if msi_target:
                target_path = msi_target

        return target_path, working_dir, icon_location
    except Exception as e:
        logger.debug("Failed to resolve shortcut %s: %s", shortcut_path, e)
        return None, None, None
    finally:
        if need_uninit:
            ole32.CoUninitialize()


def extract_exe_path_from_registry(
    display_icon: str | None, install_location: str | None, display_name: str
) -> str | None:
    """Extract or discover a valid executable target path from registry attributes.

    Args:
        display_icon: Value of the DisplayIcon registry entry.
        install_location: Value of the InstallLocation registry entry.
        display_name: Display name of the installed program.

    Returns:
        Absolute path to the executable file, or None if unresolvable.
    """
    if display_icon:
        clean_icon = display_icon.partition(",")[0].strip('"').strip()
        if clean_icon.lower().endswith(".exe") and not is_installer_or_stub(clean_icon):
            icon_path = Path(clean_icon)
            if icon_path.exists() and not is_uninstaller(display_name, str(icon_path)):
                return str(icon_path)

    if install_location:
        clean_folder = install_location.strip('"').strip()
        folder_path = Path(clean_folder)
        if folder_path.exists() and folder_path.is_dir():
            try:
                exe_files = [
                    p
                    for p in folder_path.glob("*.exe")
                    if p.is_file()
                    and not is_uninstaller(display_name, str(p))
                    and not is_installer_or_stub(str(p))
                ]
                if exe_files:
                    norm_name = display_name.lower().replace(" ", "")
                    for exe in exe_files:
                        if exe.stem.lower().replace(" ", "") in norm_name:
                            return str(exe)
                    # Only return if there is a single dedicated executable in the install directory
                    if len(exe_files) == 1:
                        return str(exe_files[0])
            except Exception as e:
                logger.debug("Failed searching executables in %s: %s", clean_folder, e)

    return None


def get_start_menu_paths() -> list[Path]:
    """Retrieve existing Start Menu directory paths for System and Current User.

    Returns:
        List of Path objects for valid Start Menu folders.
    """
    paths: list[Path] = []

    program_data = os.environ.get("ProgramData")
    if program_data:
        sys_start_menu = Path(program_data) / "Microsoft" / "Windows" / "Start Menu"
        if sys_start_menu.exists():
            paths.append(sys_start_menu)

    app_data = os.environ.get("APPDATA")
    if app_data:
        user_start_menu = Path(app_data) / "Microsoft" / "Windows" / "Start Menu"
        if user_start_menu.exists():
            paths.append(user_start_menu)

    return paths


def scan_start_menu_shortcuts() -> list[tuple[str, str, str | None, str | None]]:
    """Scan Start Menu directories for shortcut files pointing to executables.

    Returns:
        List of tuples containing (shortcut_name, target_path, working_dir, icon_location).
    """
    results: list[tuple[str, str, str | None, str | None]] = []
    start_dirs = get_start_menu_paths()

    for start_dir in start_dirs:
        logger.info("Scanning Start Menu directory: %s", start_dir)
        try:
            for shortcut_path in start_dir.rglob("*.lnk"):
                if not shortcut_path.is_file():
                    continue

                shortcut_name = shortcut_path.stem.strip()
                if not shortcut_name:
                    continue

                target_path, working_dir, icon_loc = resolve_shortcut(
                    str(shortcut_path)
                )

                if not target_path:
                    logger.debug(
                        "[DISCARD] Shortcut %s has no target_path", shortcut_name
                    )
                    continue

                if not target_path.lower().endswith(".exe"):
                    logger.debug(
                        "[DISCARD] Shortcut %s target %s is not an .exe",
                        shortcut_name,
                        target_path,
                    )
                    continue

                if not Path(target_path).exists():
                    logger.debug(
                        "[DISCARD] Shortcut %s target %s does not exist on disk",
                        shortcut_name,
                        target_path,
                    )
                    continue

                if is_uninstaller(shortcut_name, target_path):
                    logger.debug(
                        "[DISCARD] Shortcut %s target %s is flagged as uninstaller/stub",
                        shortcut_name,
                        target_path,
                    )
                    continue

                logger.info(
                    "[ACCEPTED] Shortcut '%s' -> target '%s'",
                    shortcut_name,
                    target_path,
                )
                results.append((shortcut_name, target_path, working_dir, icon_loc))
        except Exception as e:
            logger.warning("Error scanning Start Menu folder %s: %s", start_dir, e)

    return results


def read_registry_entry(key: winreg.HKEYType, name: str) -> str:
    """Retrieve a string from the registry safely.

    Args:
        key: Open registry key handle.
        name: Value name to read.

    Returns:
        The string value from the registry.

    Raises:
        ValueError: If the registry value type is not a string type.
    """
    value, reg_type = cast(tuple[str, int], winreg.QueryValueEx(key, name))

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
        with winreg.OpenKey(hive, subkey_path) as key:
            num_subkeys = winreg.QueryInfoKey(key)[0]

            for i in range(num_subkeys):
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        try:
                            name: str = read_registry_entry(subkey, "DisplayName")
                        except (OSError, ValueError):
                            continue

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

                        exe_path = extract_exe_path_from_registry(icon, folder, name)
                        if not exe_path:
                            continue

                        builder = ProgramBuilder(
                            path=exe_path,
                            name=name,
                            version=version,
                            folder=folder,
                            icon=icon,
                        )
                        programs.append(builder)
                except OSError:
                    continue
    except OSError:
        pass

    return programs


def get_programs_from_registry() -> list[ProgramBuilder]:
    """Collect programs from all required registry paths (x64, x32, Current User).

    Returns:
        A list of ProgramBuilder instances extracted from the registry.
    """
    registry_paths = [
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
        (
            winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        ),
    ]

    unique_programs: dict[str, ProgramBuilder] = {}

    for hive, path in registry_paths:
        for program in read_programs_from_registry_path(hive, path):
            if not program.path:
                continue
            canon_key = get_canonical_path(program.path)
            if canon_key not in unique_programs:
                unique_programs[canon_key] = program
            else:
                unique_programs[canon_key].merge_from_registry(
                    name=program.name,
                    version=program.version,
                    folder=program.folder,
                    icon=program.icon,
                )

    return list(unique_programs.values())


def get_all_installed_programs() -> list[Program]:
    """Retrieve all installed programs detected from Registry and Start Menu without duplicates.

    Returns:
        A list of constructed Program instances sorted alphabetically by name.
    """
    builders_map: dict[str, ProgramBuilder] = {}

    # 1. Collect programs from Registry
    logger.info("Reading installed programs from Registry...")
    registry_drafts = get_programs_from_registry()
    logger.info("Found %d program entries in Registry", len(registry_drafts))

    for draft in registry_drafts:
        if not draft.path:
            continue
        canon_key = get_canonical_path(draft.path)
        if canon_key not in builders_map:
            builders_map[canon_key] = ProgramBuilder(path=draft.path)

        builders_map[canon_key].merge_from_registry(
            name=draft.name,
            version=draft.version,
            folder=draft.folder,
            icon=draft.icon,
        )

    # 2. Collect programs from Start Menu
    logger.info("Scanning Start Menu shortcuts...")
    start_menu_shortcuts = scan_start_menu_shortcuts()
    logger.info("Accepted %d shortcuts from Start Menu", len(start_menu_shortcuts))

    for name, target_path, working_dir, icon_loc in start_menu_shortcuts:
        canon_key = get_canonical_path(target_path)
        if canon_key not in builders_map:
            builders_map[canon_key] = ProgramBuilder(path=target_path)

        builders_map[canon_key].merge_from_start_menu(
            name=name,
            folder=working_dir,
            icon=icon_loc,
        )

    # 3. Construct and sort final Program instances
    programs = [builder.build() for builder in builders_map.values()]
    programs.sort(key=lambda p: p.name.lower())

    return programs


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logger.info("Gathering information from Registry and Start Menu...")
    installed_programs = get_all_installed_programs()

    print(f"\nTotal unique programs found: {len(installed_programs)}")
    print("-" * 60)

    for idx, prog in enumerate(installed_programs, 1):
        print(f"{idx}. {prog.name}")
        print(f"   Version: {prog.version}")
        print(f"   Install directory: {prog.folder}")
        print(f"   Icon: {prog.icon}")
        print(f"   Path: {prog.path}")
        print("-" * 60)
