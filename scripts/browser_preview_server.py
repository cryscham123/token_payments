#!/usr/bin/env python3
"""Run the local Token Payments browser preview server."""

from __future__ import annotations

import argparse

from token_payments.runtime.browser_preview import (
    DEFAULT_BROWSER_PREVIEW_HOST,
    DEFAULT_BROWSER_PREVIEW_PORT,
    serve_browser_preview,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local Token Payments browser preview server.")
    parser.add_argument("--host", default=DEFAULT_BROWSER_PREVIEW_HOST, help="Host interface to bind.")
    parser.add_argument("--port", default=DEFAULT_BROWSER_PREVIEW_PORT, type=int, help="TCP port to bind.")
    args = parser.parse_args(argv)

    serve_browser_preview(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
