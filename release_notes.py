import re
import sys

version = sys.argv[1].lstrip("v")
text = open("CHANGELOG.md", encoding="utf-8").read()
match = re.search(rf"^## {re.escape(version)}\n(.*?)(?=^## |\Z)", text, re.S | re.M)
notes = match.group(1).strip() if match else ""
with open("release_notes.md", "w", encoding="utf-8") as f:
    f.write(notes + "\n")
