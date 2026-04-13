"""
Shared sys.path bootstrap. Modules are organized by role
(python/grok, python/meta_api, python/web_crawler) but still use flat
imports like `import config`, `import ig_web_client as web`,
`from xai_client import XAIClient`. Importing this module injects every
python/ subfolder onto sys.path so those imports resolve regardless of
which entry point is run.
"""

import sys
from pathlib import Path

_PYTHON_DIR = Path(__file__).resolve().parent
_EXTRA_DIRS = [
    _PYTHON_DIR,                          # config.py
    _PYTHON_DIR / "grok",                 # xai_client
    _PYTHON_DIR / "meta_api",             # instagram_client, run
    _PYTHON_DIR / "web_crawler",          # ig_web_client, auto_commenter
]

for _p in _EXTRA_DIRS:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
