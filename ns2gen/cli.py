"""Command line entry point: GUI by default, headless export with --export."""
from __future__ import annotations

import argparse
import sys

from . import __version__

TK_HELP = (
    "ns2gen needs Tkinter, which is not installed for this Python.\n"
    "  Debian/Ubuntu: sudo apt install python3-tk\n"
    "  Fedora:        sudo dnf install python3-tkinter\n"
    "  Arch:          sudo pacman -S tk\n"
    "  openSUSE:      sudo zypper install python3-tk\n"
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="ns2gen", description="Scenario generator for the ns2 network simulator.")
    p.add_argument("file", nargs="?", help="scene file (.json) to open")
    p.add_argument("--export", metavar="OUT.tcl", help="no GUI: convert FILE to a TCL script and exit")
    p.add_argument("--version", action="version", version=f"ns2gen {__version__}")
    args = p.parse_args(argv)

    if args.export:
        if not args.file:
            p.error("--export needs a scene file")
        from .model import Scene
        from .tclgen import generate
        try:
            tcl = generate(Scene.load(args.file))
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"ns2gen: {e}", file=sys.stderr)
            return 1
        with open(args.export, "w", encoding="utf-8") as fh:
            fh.write(tcl)
        print(f"wrote {args.export}")
        return 0

    try:
        from .gui import run
    except ImportError as e:
        if "tkinter" in str(e).lower() or "_tkinter" in str(e).lower():
            print(TK_HELP, file=sys.stderr)
            return 1
        raise
    run(args.file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
