#!/usr/bin/env python3
import sys, re, pathlib
p = pathlib.Path(sys.argv[1])
txt = p.read_text()
# convert leading 8+ spaces at start of recipe lines to a single TAB
txt = re.sub(r'(?m)^(?:\t|) {8,}(?=\S)', '\t', txt)
p.write_text(txt)
print("Makefile tabs normalized.")
