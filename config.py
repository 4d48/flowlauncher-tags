import logging
import os
from pathlib import Path

appdata = os.environ.get("APPDATA")

PLUGIN_KEYWORD = "tag"
PLUGIN_DATADIR = (
    (Path(appdata) / "FlowLauncher" / "Cache" / "Plugins" / "Tags")
    if appdata
    else Path(".")
)

PLUGIN_DATADIR.mkdir(parents=True, exist_ok=True)

TAGS_FILE_PATH = PLUGIN_DATADIR / "tags.json"
# PROGRAMS_FILE_PATH = PLUGIN_DATADIR / "programs.json"

ICON_MISSING_PATH = Path("images") / "icon_missing.png"

ICON_CACHE_DIR = PLUGIN_DATADIR / "icon_cache"
ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# largest score value in FlowLauncher (2^31 - 1)
MAX_SCORE: int = 2_147_483_647

logger = logging.getLogger("tags_plugin")
logger.setLevel(logging.WARNING)

logger.propagate = False

file_handler = logging.FileHandler(PLUGIN_DATADIR / "plugin.log", encoding="utf-8")
file_handler.setLevel(logging.WARNING)

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
