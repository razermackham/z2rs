#!/usr/bin/env python3
"""Write a local-source, fork-aware copy of the pinned Flatpak manifest.

The checked-in manifest builds the upstream ``troyedwardsjr/z2rs`` release. For
local and CI builds of the current tree, this script:

* replaces that git source with the repository checkout,
* rewrites the app ID and metadata for the repository it is built from, so a
  fork gets ``io.github.<owner>.<repo>`` instead of the upstream ID, and
* writes ``io.github.troyedwardsjr.z2rs.local.json`` next to the pinned
  manifest.

The generated manifest and metadata are gitignored.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
MANIFEST = HERE / "io.github.troyedwardsjr.z2rs.json"
OUTPUT = HERE / "io.github.troyedwardsjr.z2rs.local.json"
GENERATED = HERE / "generated"

UPSTREAM_OWNER = "troyedwardsjr"
UPSTREAM_REPO = "z2rs"
UPSTREAM_APP_ID = f"io.github.{UPSTREAM_OWNER}.{UPSTREAM_REPO}"

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
]


def git_origin() -> tuple[str, str] | None:
    """Return ``(owner, repo)`` parsed from the ``origin`` remote, if any."""
    try:
        url = subprocess.check_output(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=REPO,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    if not url:
        return None
    if url.endswith(".git"):
        url = url[:-4]
    match = re.search(r"(?:[:/])([^/:]+)/([^/]+)$", url)
    if match is None:
        return None
    return match.group(1), match.group(2)


def identity() -> tuple[str, str, str, str]:
    """Return ``(owner, repo, repo_url, ref)`` for this checkout."""
    origin = git_origin()
    owner = os.environ.get("FLATPAK_OWNER") or (origin[0] if origin else UPSTREAM_OWNER)
    repo = os.environ.get("FLATPAK_REPO") or (origin[1] if origin else UPSTREAM_REPO)
    repo_url = (
        os.environ.get("FLATPAK_REPO_URL")
        or f"https://github.com/{owner}/{repo}"
    )
    ref = os.environ.get("FLATPAK_REF") or "HEAD"
    return owner, repo, repo_url, ref


def app_component(value: str, fallback: str) -> str:
    """Make one valid, lowercase Flatpak/D-Bus app-ID component."""
    value = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = fallback
    if not value[0].isalpha():
        value = f"x{value}"
    return value


def rewrite_desktop(text: str, app_id: str, display_name: str) -> str:
    text = re.sub(r"(?m)^Name=.*$", f"Name={display_name}", text, count=1)
    text = re.sub(r"(?m)^Icon=.*$", f"Icon={app_id}", text, count=1)
    return text


def rewrite_metainfo(
    text: str, app_id: str, display_name: str, owner: str, repo_url: str, ref: str
) -> str:
    text = re.sub(r"<id>[^<]*</id>", f"<id>{app_id}</id>", text, count=1)
    text = re.sub(
        r'(<launchable type="desktop-id">)[^<]*(</launchable>)',
        rf"\g<1>{app_id}.desktop\g<2>",
        text,
        count=1,
    )
    text = re.sub(r"<name>[^<]*</name>", f"<name>{display_name}</name>", text, count=1)
    text = re.sub(
        r'(<url type="homepage">)[^<]*(</url>)',
        rf"\g<1>{repo_url}\g<2>",
        text,
        count=1,
    )
    text = re.sub(
        r'(<url type="bugtracker">)[^<]*(</url>)',
        rf"\g<1>{repo_url}/issues\g<2>",
        text,
        count=1,
    )
    text = re.sub(
        r'(<url type="help">)[^<]*(</url>)',
        rf"\g<1>{repo_url}/tree/{ref}/guide\g<2>",
        text,
        count=1,
    )
    text = re.sub(
        r"(<developer>\s*<name>)[^<]*(</name>)",
        rf"\g<1>{owner}\g<2>",
        text,
        count=1,
    )
    return text


def main() -> None:
    owner, repo, repo_url, ref = identity()
    app_id = (
        f"io.github.{app_component(owner, 'user')}."
        f"{app_component(repo, 'app')}"
    )
    display_name = repo.strip() or app_component(repo, "app")

    # Recreate the generated metadata so a previous fork's files never linger.
    if GENERATED.exists():
        shutil.rmtree(GENERATED)
    GENERATED.mkdir()

    desktop = HERE / f"{UPSTREAM_APP_ID}.desktop"
    metainfo = HERE / f"{UPSTREAM_APP_ID}.metainfo.xml"
    icon = HERE / f"{UPSTREAM_APP_ID}.svg"

    (GENERATED / f"{app_id}.desktop").write_text(
        rewrite_desktop(desktop.read_text(), app_id, display_name)
    )
    (GENERATED / f"{app_id}.metainfo.xml").write_text(
        rewrite_metainfo(
            metainfo.read_text(), app_id, display_name, owner, repo_url, ref
        )
    )
    shutil.copyfile(icon, GENERATED / f"{app_id}.svg")

    data = json.loads(MANIFEST.read_text())
    data["app-id"] = app_id

    # Local test ROMs, movies and patches are never part of a build.
    skip = list(SKIP)
    for pattern in ("*.nes", "*.ips", "*.fm2", "*.bk2", "*.zip", "*.patch"):
        skip.extend(sorted(p.name for p in REPO.glob(pattern)))
    skip = list(dict.fromkeys(skip))

    module = data["modules"][0]
    module["build-commands"] = [
        command.replace(UPSTREAM_APP_ID, app_id)
        for command in module["build-commands"]
    ]

    sources = []
    found_git = False
    for source in module["sources"]:
        if isinstance(source, dict) and source.get("type") == "git":
            sources.append({"type": "dir", "path": "../..", "skip": skip})
            found_git = True
        elif isinstance(source, dict) and source.get("type") == "file" and source.get(
            "path"
        ) in {
            f"{UPSTREAM_APP_ID}.desktop",
            f"{UPSTREAM_APP_ID}.metainfo.xml",
            f"{UPSTREAM_APP_ID}.svg",
        }:
            continue
        else:
            sources.append(source)
    if not found_git:
        raise SystemExit("the pinned manifest has no git source to replace")

    sources.extend(
        [
            {
                "type": "file",
                "path": f"generated/{app_id}.desktop",
                "dest-filename": f"{app_id}.desktop",
            },
            {
                "type": "file",
                "path": f"generated/{app_id}.metainfo.xml",
                "dest-filename": f"{app_id}.metainfo.xml",
            },
            {
                "type": "file",
                "path": f"generated/{app_id}.svg",
                "dest-filename": f"{app_id}.svg",
            },
        ]
    )
    module["sources"] = sources

    OUTPUT.write_text(json.dumps(data, indent=4) + "\n")
    print(f"wrote {OUTPUT} (app-id {app_id})")


if __name__ == "__main__":
    main()
