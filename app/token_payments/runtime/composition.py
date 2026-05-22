"""Public live runtime composition facade.

The implementation lives in ``composition_impl`` so this public import path can
remain a small composition root for API, worker, and entrypoint contracts.
"""

from __future__ import annotations

from . import composition_impl as _impl
from .composition_impl import *  # noqa: F401,F403


def _export_impl_symbols() -> None:
    for name in dir(_impl):
        if name.startswith("__"):
            continue
        globals().setdefault(name, getattr(_impl, name))


def _preserve_public_module_path() -> None:
    for name in getattr(_impl, "__all__", ()):
        value = globals().get(name)
        if getattr(value, "__module__", None) == _impl.__name__:
            value.__module__ = __name__


_export_impl_symbols()
_preserve_public_module_path()


_ROUTE_HELPER_NAMES = (
    "register_auth_routes",
    "register_order_routes",
    "register_checkout_routes",
    "register_payment_routes",
    "register_store_catalog_routes",
    "register_store_owner_inventory_routes",
    "register_merchant_membership_routes",
    "register_operator_routes",
    "register_operator_action_routes",
)


def build_live_api_router(*args, **kwargs):
    """Build the live router while honoring facade-level helper overrides."""

    for name in _ROUTE_HELPER_NAMES:
        setattr(_impl, name, globals()[name])
    return _impl.build_live_api_router(*args, **kwargs)


build_live_api_router.__module__ = __name__

__all__ = tuple(getattr(_impl, "__all__", ()))
