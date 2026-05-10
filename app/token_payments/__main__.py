"""Runtime entry point for the Token Payments application."""

from __future__ import annotations

import sys
from typing import Sequence

from .runtime import dispatch_runtime_command


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    result = dispatch_runtime_command(args)
    print(result.to_json())
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
