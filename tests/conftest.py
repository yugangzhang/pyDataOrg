"""The base package is tested on its own: installed project plugins (which
register their own servers, campaigns and analyses) are not loaded."""

import os

os.environ["PYDATAORG_PLUGINS"] = "none"
