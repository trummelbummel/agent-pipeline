from __future__ import annotations

import logging

from compliance.config.settings import AppConfig


def configure_logging(config: AppConfig) -> None:
    """Apply ``config.logging`` level and format via ``logging.basicConfig``.

    :param config: Loaded application config with a ``logging`` section.
    """
    level_name = config.logging.level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format=config.logging.format)
