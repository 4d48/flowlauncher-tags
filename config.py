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

ICON_MISSING_PATH = Path("Images") / "icon_missing.png"

ICON_CACHE_DIR = PLUGIN_DATADIR / "icon_cache"
ICON_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# largest score value in FlowLauncher (2^31 - 1)
MAX_SCORE: int = 2_147_483_647

logging.basicConfig(
    filename=PLUGIN_DATADIR / "plugin.log",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)
