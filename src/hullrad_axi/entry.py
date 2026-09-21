from __future__ import annotations

import sys

from .version import VERSION


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) == 1 and argv[0] in {"-v", "-V", "--version"}:
        print(VERSION)
        return
    from .cli import emit
    from .cli import main as cli_main

    try:
        cli_main(argv)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception:  # noqa: BLE001 - the agent interface must never leak a traceback
        emit({"error": "hullrad-axi encountered an unexpected internal error", "help": "Check the supplied paths, then rerun the command with --help"})
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
