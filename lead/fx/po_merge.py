"""Three-way merge of Lingui catalog translations across package branches.

Usage: po_merge.py <repo> <base-ref> <branch> [<branch> ...]

For apps/web/src/i18n/locales/ar/messages.po in <repo>'s working tree (already re-extracted
from the merged code): every entry takes the translation a branch gave it, when that branch
changed it relative to <base-ref> or added it. Two branches that changed the same entry to
different texts are reported and the first one wins. Entries left without Arabic are listed.
"""

import json
import subprocess
import sys

PO = "apps/web/src/i18n/locales/ar/messages.po"


def unquote(line: str) -> str:
    return json.loads(line[line.index('"') : line.rindex('"') + 1])


def quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def parse(text: str):
    """Yield (start, end, key, msgstr, msgstr_start) per entry; lines are 0-based, end exclusive."""
    lines = text.split("\n")
    entries = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        ctx, msgid, msgstr, field, str_start = None, None, None, None, None
        while i < len(lines) and lines[i].strip():
            line = lines[i]
            if line.startswith("msgctxt "):
                ctx, field = unquote(line), "ctx"
            elif line.startswith("msgid "):
                msgid, field = unquote(line), "id"
            elif line.startswith("msgstr "):
                msgstr, field, str_start = unquote(line), "str", i
            elif line.startswith('"'):
                part = unquote(line)
                if field == "ctx":
                    ctx += part
                elif field == "id":
                    msgid += part
                elif field == "str":
                    msgstr += part
            i += 1
        if msgid is not None and msgstr is not None:
            entries.append((start, i, (ctx, msgid), msgstr, str_start))
    return lines, entries


def table(text: str) -> dict:
    return {key: value for _, _, key, value, _ in parse(text)[1] if key[1]}


def show(repo: str, ref: str) -> str:
    return subprocess.run(
        ["git", "-C", repo, "show", f"{ref}:{PO}"], capture_output=True, text=True, check=True
    ).stdout


def main() -> int:
    repo, base_ref, *branches = sys.argv[1:]
    base = table(show(repo, base_ref))
    changes: dict = {}
    conflicts = []
    for branch in branches:
        for key, value in table(show(repo, branch)).items():
            if not value or base.get(key) == value:
                continue
            if key in changes and changes[key][0] != value:
                conflicts.append((key, changes[key], (value, branch)))
                continue
            changes.setdefault(key, (value, branch))
    path = f"{repo}/{PO}"
    lines, entries = parse(open(path, encoding="utf-8").read())
    applied, missing = 0, []
    for _start, end, key, value, str_start in reversed(entries):
        if not key[1]:
            continue
        wanted = changes.get(key, (value, None))[0]
        if wanted != value:
            lines[str_start:end] = [f"msgstr {quote(wanted)}"]
            applied += 1
        if not wanted:
            missing.append(key)
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    print(f"applied {applied} translations from {len(branches)} branches")
    for key, first, second in conflicts:
        print(f"CONFLICT {key!r}: kept {first[0]!r} ({first[1]}), dropped {second[0]!r} ({second[1]})")
    for key in reversed(missing):
        print(f"MISSING {key!r}")
    return 1 if conflicts or missing else 0


if __name__ == "__main__":
    sys.exit(main())
