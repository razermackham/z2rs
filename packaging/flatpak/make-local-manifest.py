#!/usr/bin/env python3
"""Write a local-source copy of the pinned Flatpak manifest.

The checked-in manifest builds a released tag. For local and CI builds of the
current tree, this replaces that git source with the repository checkout and
writes ``io.github.troyedwardsjr.z2rs.local.json`` next to the pinned manifest.
The generated file is gitignored.
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
MANIFEST = HERE / "io.github.troyedwardsjr.z2rs.json"
OUTPUT = HERE / "io.github.troyedwardsjr.z2rs.local.json"

# Build output, VCS data, local tooling, and the packaging directory itself.
# The manifest's file sources are separate entries, so skipping this directory
# in the checkout source does not remove them from the build.
SKIP = [
    ".git",
    ".flatpak-builder",
    ".emucap",
    "flatpak_app",
    "node_modules",
    "packaging/flatpak",
    "repo",
    "target",
    "venv",
    "z2rs-flatpak.zip",
    "noflash.patch",
]


def main() -> None:
    data = json.loads(MANIFEST.read_text())

    # Local test ROMs and movies are never part of a build.
    skip = list(SKIP)
    for pattern in ("*.nes", "*.ips", "*.fm2", "*.bk2"):
        skip.extend(sorted(p.name for p in REPO.glob(pattern)))
    skip = list(dict.fromkeys(skip))

    module = data["modules"][0]
    sources = []
    found = False
    for source in module["sources"]:
        if isinstance(source, dict) and source.get("type") == "git":
            sources.append({"type": "dir", "path": "../..", "skip": skip})
            found = True
        else:
            sources.append(source)
    if not found:
        raise SystemExit("the pinned manifest has no git source to replace")

    module["sources"] = sources
    OUTPUT.write_text(json.dumps(data, indent=4) + "\n")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
