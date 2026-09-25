"""FastAPI application factory with lifespan pipeline DI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI

from compliance.config.settings import AppConfig, load_config
from compliance.llm.chat import ChatFn
from compliance.workflows.claim_pipeline import ClaimPipeline
from compliance.workflows.pipeline import PreprocessingPipeline


class AppState(TypedDict):
    """Lifespan-yielded resources shared across requests.

    :param config: Loaded or injected application configuration.
    :param preprocessing: Shared PreprocessingPipeline instance.
    :param claims: Shared ClaimPipeline instance.
    """

    config: AppConfig
    preprocessing: PreprocessingPipeline
    claims: ClaimPipeline


def create_app(
    config: AppConfig | None = None,
    *,
    chat_fn: ChatFn | None = None,
) -> FastAPI:
    """Build a FastAPI app with lifespan-injected pipelines.

    :param config: Optional AppConfig; when None, loads ``config.yaml``.
    :param chat_fn: Optional shared chat seam injected into ClaimPipeline (tests).
    :return: Configured FastAPI application.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[AppState]:
        resolved = config if config is not None else load_config("config.yaml")
        state: AppState = {
            "config": resolved,
            "preprocessing": PreprocessingPipeline(resolved),
            "claims": ClaimPipeline(resolved, chat_fn=chat_fn),
        }
        yield state

    return FastAPI(lifespan=lifespan)
