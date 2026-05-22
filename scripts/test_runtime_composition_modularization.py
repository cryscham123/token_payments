from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


def test_runtime_composition_facade_is_thin_and_reexports_public_contracts() -> None:
    source = (ROOT / "app/token_payments/runtime/composition.py").read_text(encoding="utf-8")
    lines = source.splitlines()

    assert len(lines) < 180
    assert "from .composition_impl import" in source

    composition = importlib.import_module("token_payments.runtime.composition")
    assert composition.LiveRuntimeConfig.__module__ == "token_payments.runtime.composition"
    assert composition.LiveApiComposition.__module__ == "token_payments.runtime.composition"
    assert callable(composition.build_live_api_facades)
    assert callable(composition.build_live_api_router)
    assert callable(composition.build_live_worker_runtime_from_env)


def test_runtime_composition_context_modules_are_importable_without_starting_drivers() -> None:
    expected_modules = {
        "token_payments.runtime.composition_auth",
        "token_payments.runtime.composition_store_catalog",
        "token_payments.runtime.composition_inventory",
        "token_payments.runtime.composition_order",
        "token_payments.runtime.composition_payment",
        "token_payments.runtime.composition_checkout",
        "token_payments.runtime.composition_api",
    }

    imported = {module_name: importlib.import_module(module_name) for module_name in expected_modules}

    assert imported["token_payments.runtime.composition_auth"].FACTORY_CONTEXT == "auth"
    assert imported["token_payments.runtime.composition_store_catalog"].FACTORY_CONTEXT == "store_catalog"
    assert imported["token_payments.runtime.composition_inventory"].FACTORY_CONTEXT == "inventory"
    assert imported["token_payments.runtime.composition_order"].FACTORY_CONTEXT == "order"
    assert imported["token_payments.runtime.composition_payment"].FACTORY_CONTEXT == "payment"
    assert imported["token_payments.runtime.composition_checkout"].FACTORY_CONTEXT == "checkout"
    assert imported["token_payments.runtime.composition_api"].FACTORY_CONTEXT == "api"


def test_runtime_composition_impl_is_not_the_public_import_path() -> None:
    composition = importlib.import_module("token_payments.runtime.composition")
    impl = importlib.import_module("token_payments.runtime.composition_impl")

    assert composition.LiveRuntimeConfig is impl.LiveRuntimeConfig
    assert composition.LiveRuntimeConfig.__module__ == "token_payments.runtime.composition"
