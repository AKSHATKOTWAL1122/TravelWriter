"""Endpoint modules (spec 01.4, ISSUE-053).

Every module in this folder is imported here, so its routes register on the shared
api_router before main.py includes it. An endpoint spec only adds a file here and
never edits main.py.
"""

import importlib
import pkgutil

for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")
