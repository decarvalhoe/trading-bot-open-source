#!/usr/bin/env python3
import pathlib
import re
import sys


def normalize_makefile_tabs(path: pathlib.Path) -> None:
    text = path.read_text()
    updated = re.sub(r"(?m)^(\t| {8,})(?=\S)", "\t", text)
    path.write_text(updated)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: fix_make_tabs.py <Makefile>", file=sys.stderr)
        raise SystemExit(1)
    normalize_makefile_tabs(pathlib.Path(sys.argv[1]))
    print("Makefile tabs normalized.")


if __name__ == "__main__":
    main()
