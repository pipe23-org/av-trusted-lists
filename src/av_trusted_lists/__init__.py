"""Archive of the EU age-verification trusted lists and a page built from it."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("av-trusted-lists")
except PackageNotFoundError:  # pragma: no cover - not installed (editable source tree)
    __version__ = "0.0.0"
