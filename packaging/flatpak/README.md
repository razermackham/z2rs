# Flatpak packaging

This directory holds the Flatpak metadata for z2rs. The manifest is written in
the style Flathub expects, but z2rs is not submitted to Flathub. The GitHub
Actions workflow in `.github/workflows/flatpak.yml` builds the bundles.

The package contains the launcher, the game and the co-op signalling server. It
does **not** contain a ROM. Players supply their own Zelda II (USA) dump.

## Contents

| File | Purpose |
| --- | --- |
| `io.github.troyedwardsjr.z2rs.json` | Pinned, Flathub-style manifest. Builds the `v0.6.0` tag. |
| `make-local-manifest.py` | Writes the gitignored `*.local.json` that builds the current checkout. |
| `cargo-sources.json` | Vendored crate sources for `cargo --offline`. Generated from `Cargo.lock`. |
| `io.github.troyedwardsjr.z2rs.desktop` | Desktop entry. |
| `io.github.troyedwardsjr.z2rs.metainfo.xml` | AppStream metadata. |
| `io.github.troyedwardsjr.z2rs.svg` | Application icon. |

The checked-in manifest deliberately pins a released tag so it can be built
outside CI. The workflow generates a temporary `*.local.json` next to it whose
`git` source is replaced by the checkout being built. Generated local manifests
are gitignored and must not be committed.

## Building locally

Install Flatpak and `flatpak-builder`, then install the runtime and SDK used by
the manifest:

```sh
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install flathub org.freedesktop.Platform//25.08 org.freedesktop.Sdk//25.08 \
    org.freedesktop.Sdk.Extension.rust-stable//25.08
```

Build and install the pinned release:

```sh
flatpak-builder --user --install --force-clean build-dir \
    packaging/flatpak/io.github.troyedwardsjr.z2rs.json
flatpak run io.github.troyedwardsjr.z2rs
```

To test uncommitted changes, generate the local-source manifest and build
that instead:

```sh
python3 packaging/flatpak/make-local-manifest.py
flatpak-builder --user --install --force-clean build-dir \
    packaging/flatpak/io.github.troyedwardsjr.z2rs.local.json
```

The script swaps the pinned `git` source for the repository checkout and skips
build output, VCS data and local ROM/movie files. The generated `*.local.json`
file is gitignored.

## Sandbox permissions

The manifest is intentionally narrow. It has no blanket host, home or
removable-media access. Files are chosen through the XDG desktop portal, which
grants access only to the file the player picks.

| Permission | Why |
| --- | --- |
| `--share=ipc` | Required by the windowing stack. |
| `--share=network` | Online co-op and the signalling server. |
| `--socket=wayland`, `--socket=fallback-x11` | Window and input. |
| `--socket=pulseaudio` | Sound. |
| `--device=dri` | GPU rendering. |
| `--device=input` | Gamepads (`/dev/input`). Needs Flatpak 1.15.6 or newer. |
| `--filesystem=xdg-run/discord-ipc-0` | Discord Rich Presence, when z2rs is configured to use it. |

Portal APIs are available to sandboxed apps by default, so the manifest does not
request `--talk-name=org.freedesktop.portal.*`. Do not add `--filesystem=host`,
`--filesystem=home` or `--filesystem=removable-media`; those defeat the point of
the sandbox.

## ROM caching

Picking a file through the portal returns a path under `/run/user/<uid>/doc/...`
that stops working after a restart. The launcher therefore copies the chosen
ROM into its data directory:

```
~/.var/app/io.github.troyedwardsjr.z2rs/data/z2rs/rom/game.nes
```

The copy is made when the file is picked and refreshed on Play while the
original is still readable. Later launches use the cached copy even if the
original host file is gone, so the player only has to choose it once. Only a
file with an iNES header is accepted. The launcher still records the original
path in `launcher.json` for display and for re-copying.

The cached ROM lives in the app's private data directory. It is never uploaded
by z2rs.

## HD graphics packs

HD packs picked through the portal are **not** copied into the data directory.
A portal path can disappear after a restart, so put packs where the launcher can
always find them:

```
~/.var/app/io.github.troyedwardsjr.z2rs/data/z2rs/packs/<pack>/
```

Select that folder in the launcher, or re-pick the pack after a restart. Packs
are optional and are not included in the bundle.

## Discord Rich Presence

Discord exposes its IPC socket at `$XDG_RUNTIME_DIR/discord-ipc-0`, which is why
the manifest grants exactly that path. If z2rs' Discord integration is disabled
or Discord is not running, the permission is simply unused.

## Architectures

CI builds `x86_64` and `aarch64` by default.

- Manual runs: turn off the `build_aarch64` workflow input.
- Tag builds: set the repository variable `FLATPAK_AARCH64` to `false`.

The `x86_64` build runs on `ubuntu-latest`; `aarch64` runs natively on
`ubuntu-24.04-arm`. The resulting bundles are attached to the GitHub release on
tag builds and uploaded as workflow artifacts on manual runs.

## Updating the package

When the version changes:

1. Update the `git` source `tag` and `commit` in the manifest to the new release.
2. Update the release entries and `url type="help"` in the metainfo file.
3. Regenerate `cargo-sources.json` after any dependency change:

   ```sh
   .cargo/flatpak-cargo-generator.py Cargo.lock \
       -o packaging/flatpak/cargo-sources.json
   ```

   The generator needs `aiohttp`, `PyYAML` and `tomlkit` (for example
   `python3 -m pip install aiohttp pyyaml tomlkit`).
4. Rebuild locally or run the workflow manually before tagging.
