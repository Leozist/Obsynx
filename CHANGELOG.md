# Changelog

---

## v1.2.0 — 2026-04-06

### Fixed
- Watcher `resolve_parent` now validates cached folder page IDs against Notion before using them. Archived or deleted folder pages no longer cause 400 errors on push.
- Watcher searches for existing non-archived Notion pages before creating new folder pages, preventing duplicate folder creation on repeated saves.

---

## v1.1.0 — 2026-04-05

### Added
- **Duplicate page prevention** — push script now checks if a page with the same title already exists under the same parent before creating a new one. Existing pages are cleared and rewritten instead of duplicated.
- **Notion existence verification** — before skipping an unchanged file, the push script verifies the page actually exists in Notion. If it was deleted or never pushed correctly, it re-pushes automatically regardless of local state.
- **Reconfigure option** — running the installer after setup allows updating any individual config field (API keys, vault path, image folders, backup settings, watcher mode) without a full reinstall. Rewrote using a temp Python script to avoid bash argument escaping issues with special characters in API keys.
- **Verify API keys option** — tests Notion API key, Notion root page accessibility, Cloudinary credentials, and vault path. Prints pass or fail for each.
- **Uninstall option** — full removal of scripts, config, watcher service, PATH entries and shell config. Backups are preserved at `~/.obsynx-backups/`.
- **Windows installer** (`install_windows.py`) — native Python installer for Windows. No WSL required. Sets up Task Scheduler for the file watcher, adds `obsynx` to user PATH via registry, includes reconfigure, verify and uninstall options.
- **OS selection at install time** — installer asks whether you are on Debian-based Linux or Windows and branches accordingly.

### Fixed
- Installer now correctly detects zsh vs bash and writes PATH and watcher auto-start entries to the right shell config file.
- Running the installer with `sudo` no longer silently installs everything to `/root/` instead of the user's home directory.
- Image filename collisions during Notion pull — each downloaded image now gets a unique filename using a block ID hash, preventing multiple images from overwriting each other.
- Duplicate folder nesting (`CRTP/CRTP/Lab`) during pull — fixed the top-level page walker to avoid creating an extra folder level.

---

## v1.0.0 — 2026-03-29

### Initial release

- **Obsidian → Notion push** — uploads entire vault to Notion preserving folder structure as nested pages. Tracks file modification times to skip unchanged files on subsequent runs.
- **Notion → Obsidian pull** — fetches all Notion pages and writes them as markdown files mirroring the folder structure. Latest content wins on conflict using a two-factor check: size difference greater than 10% means larger file wins, otherwise newer timestamp wins.
- **Cloudinary image hosting** — local images uploaded to Cloudinary on push, cached locally to prevent re-uploads. Images pasted directly into Notion downloaded to vault on pull.
- **Multi-folder image search** — searches all configured screenshot folders when resolving image references in notes.
- **Code block chunking** — large code blocks split into 1900-character chunks to stay within Notion's 2000 character per block limit.
- **Obsidian tag support** — `#TagName` on its own line converted to a purple callout block in Notion and restored on pull.
- **Rolling backups** — vault backup created before every pull, oldest backup removed when limit is exceeded.
- **File watcher** — monitors vault for markdown saves and auto-pushes to Notion after a 3-second debounce. Configured at install time as systemd service or screen session.
- **Single command interface** — `obsynx push`, `obsynx pull`, `obsynx status`, `obsynx restore`, `obsynx help`.
- **Config file** — all settings stored in `~/.obsidian-sync/config.json` with owner-only permissions. No hardcoded credentials in any script.
