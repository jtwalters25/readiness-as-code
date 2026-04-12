"""Plugin registry with auto-discovery.

Walks the `ready.plugins` package, imports every `*_plugin.py` module,
instantiates each `VerificationPlugin` subclass, and indexes them by
`method_name`. The engine calls `build_default_registry()` once at
scan start and dispatches each checkpoint through it.
"""

import importlib
import pkgutil
from typing import Optional

from ready.plugins.base import VerificationPlugin


class PluginRegistry:
    """Maps verification method names to plugin instances."""

    def __init__(self) -> None:
        self._plugins: dict[str, VerificationPlugin] = {}

    def register(self, plugin: VerificationPlugin) -> None:
        if not plugin.method_name:
            raise ValueError(
                f"Plugin {plugin.__class__.__name__} has no method_name"
            )
        self._plugins[plugin.method_name] = plugin

    def get(self, method_name: str) -> Optional[VerificationPlugin]:
        return self._plugins.get(method_name)

    def methods(self) -> list[str]:
        return sorted(self._plugins.keys())

    def __contains__(self, method_name: str) -> bool:
        return method_name in self._plugins


def build_default_registry() -> PluginRegistry:
    """Discover every plugin under `ready.plugins` and return a registry."""
    registry = PluginRegistry()
    package_name = "ready.plugins"
    package = importlib.import_module(package_name)

    for _finder, module_name, _ispkg in pkgutil.iter_modules(package.__path__):
        if not module_name.endswith("_plugin"):
            continue
        full_name = f"{package_name}.{module_name}"
        module = importlib.import_module(full_name)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, VerificationPlugin)
                and attr is not VerificationPlugin
            ):
                instance = attr()
                if instance.method_name:
                    registry.register(instance)

    return registry
