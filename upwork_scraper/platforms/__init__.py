"""Platform adapter layer."""

from .base import PlatformAdapter
from .registry import build_platform_adapters

__all__ = ["PlatformAdapter", "build_platform_adapters"]
