"""FastAPI Depends helpers reading lifespan AppState from request.state."""

from __future__ import annotations

from typing import cast

from fastapi import Request

from compliance.config.settings import AppConfig
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline


def get_config(request: Request) -> AppConfig:
    """Return the AppConfig yielded by the application lifespan.

    :param request: Current FastAPI request (state populated by lifespan).
    :return: Shared application configuration.
    """
    return cast(AppConfig, request.state["config"])


def get_preprocessing(request: Request) -> PreprocessingPipeline:
    """Return the PreprocessingPipeline yielded by the application lifespan.

    :param request: Current FastAPI request (state populated by lifespan).
    :return: Shared preprocessing pipeline instance.
    """
    return cast(PreprocessingPipeline, request.state["preprocessing"])


def get_claims(request: Request) -> ClaimPipeline:
    """Return the ClaimPipeline yielded by the application lifespan.

    :param request: Current FastAPI request (state populated by lifespan).
    :return: Shared claim-analysis pipeline instance.
    """
    return cast(ClaimPipeline, request.state["claims"])
