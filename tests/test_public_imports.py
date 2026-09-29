from __future__ import annotations

import importlib
import pkgutil

import pytest

# Mirrors [tool.hatch.build.targets.wheel] packages in pyproject.toml.
PUBLIC_PACKAGES: tuple[str, ...] = ("api", "compliance", "evaluation")

# The force-included src/main.py behind the compliance-preprocess script.
ENTRYPOINT_MODULES: tuple[str, ...] = ("main",)


def _reraise_walk_error(name: str) -> None:
    """Re-raise the import error pkgutil.walk_packages just caught.

    pkgutil.walk_packages invokes onerror from inside its except block when a
    subpackage fails to import; without an onerror callback it otherwise
    silently skips that subpackage, turning a broken import into a false
    green. Re-raising here turns it into a hard collection error instead.

    :param name: Dotted name of the module that failed to import.
    """
    raise


def _public_module_names() -> list[str]:
    """Enumerate every public module that must import cleanly.

    :return: Sorted dotted module names covering the entrypoint modules and
        every module reachable by walking the public packages, excluding
        any `__main__` module (importing one executes a CLI at import time).
    """
    names = list(ENTRYPOINT_MODULES)
    for package_name in PUBLIC_PACKAGES:
        package = importlib.import_module(package_name)
        names.append(package_name)
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}.", onerror=_reraise_walk_error):
            if info.name.endswith(".__main__"):
                continue
            names.append(info.name)
    return sorted(names)


@pytest.mark.parametrize("module_name", _public_module_names())
def test_public_module_imports(module_name: str) -> None:
    """Import a public module and confirm its declared exports resolve.

    :param module_name: Dotted public module path whose import and
        `__all__` exports must resolve.
    """
    module = importlib.import_module(module_name)
    missing = [name for name in getattr(module, "__all__", ()) if not hasattr(module, name)]
    assert missing == []
