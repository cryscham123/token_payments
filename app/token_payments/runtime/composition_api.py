"""API runtime composition exports."""

from __future__ import annotations

from .composition_impl import LiveApiFacades, build_live_api_facades, build_live_api_router


FACTORY_CONTEXT = "api"

__all__ = ["FACTORY_CONTEXT", "LiveApiFacades", "build_live_api_facades", "build_live_api_router"]
