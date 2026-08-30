# Obsynx

Obsynx is a two-way sync tool that keeps your Obsidian vault and Notion workspace in sync. Notes saved in Obsidian push to Notion automatically. Notes created or edited in Notion pull back to your vault on demand. Images sync in both directions.

---

## Requirements

- Python 3.10+
- Notion integration token from notion.com/my-integrations
- Cloudinary account
- Debian/Ubuntu Linux, macOS, or Windows (native Python)

---

## Installation

**Linux:**
```bash
git clone https://github.com/Leozist/Obsynx.git
cd Obsynx
chmod +x install.sh
./install.sh
```

**macOS:**
```bash
git clone https://github.com/Leozist/Obsynx.git
cd Obsynx
chmod +x install_macos.sh
./install_macos.sh
```

**Windows:**
```bash
git clone https://github.com/Leozist/Obsynx.git
cd Obsynx
python install_windows.py
```

The installer handles dependencies, config, and the `obsynx` command. Open a new terminal when it finishes.

On macOS and Linux, install asks whether to turn on the **auto-push watcher** — it defaults to **off**. Leave it off to only push/pull when you run `obsynx push` / `obsynx pull` yourself. Pulling from Notion is always manual, on every platform, watcher on or off.

---

## Commands

```
obsynx push      Upload changed vault files to Notion
obsynx pull      Back up vault then pull Notion changes
obsynx status    View tracked files, cache, backups and logs
obsynx restore   Interactively restore a backup
obsynx help      Show usage
```

---

## Installer Options

Running the installer after setup gives you additional options:

```
[1] Fresh install
[2] Reconfigure       — Update any individual setting without reinstalling,
                         including turning the auto-push watcher on or off
[3] Verify API keys   — Test Notion, Notion page, Cloudinary and vault path
[4] Uninstall         — Full removal, backups preserved
```

---

## Features

**File watcher (optional, off by default)** pushes saved markdown files to Notion within seconds. You're asked at install time whether to turn it on — say no to keep push/pull fully manual. Runs as a systemd service or screen session on Linux, a launchd agent or screen session on macOS, Task Scheduler on Windows. Notion is never pulled automatically on any platform, watcher on or off — `obsynx pull` is always something you run yourself.

**Duplicate prevention** checks whether a page already exists in Notion before creating a new one. Existing pages are updated in place rather than duplicated.

**Notion existence verification** confirms a page is actually present in Notion before skipping it on push. If a page was deleted or never created properly, it gets re-pushed automatically regardless of local state.

**Image sync** uploads local images to Cloudinary once and caches the URLs. Images pasted into Notion are downloaded to your vault on pull.

**Conflict resolution** checks size first. Larger file wins. If sizes are close, newer timestamp wins.

**Rolling backups** run before every pull. You set the limit at install and old backups rotate out automatically.

**Code block chunking** splits large code blocks into multiple Notion blocks to stay within Notion's 2000 character per block limit.

**Multi-folder image search** searches all configured screenshot folders when resolving image references.

---

## File Structure

```
~/.obsidian-sync/
    config.json           API keys and settings (chmod 600)
    push_state.json       Tracks pushed files
    pull_state.json       Tracks pulled Notion pages
    img_cache.json        Maps filenames to Cloudinary URLs
    logs/
        sync.log
        watcher.log
    backups/
        vault_YYYYMMDD_HHMMSS/
```

---

## Watcher

Only present if you enabled automation at install (or turned it on later via Reconfigure).

**systemd (Linux):**
```bash
systemctl --user status obsynx-watcher
systemctl --user restart obsynx-watcher
```

**launchd (macOS):**
```bash
launchctl list | grep obsynx
launchctl unload -w ~/Library/LaunchAgents/com.obsynx.watcher.plist
launchctl load -w ~/Library/LaunchAgents/com.obsynx.watcher.plist
```

**screen (Linux/macOS):**
```bash
screen -r obsynx-watcher
```

---

## Uninstall

Run `./install.sh` and select `[4] Uninstall`. Your vault, Notion pages, Cloudinary images and backups are preserved.

---

## Notes

Deleting a local file does not remove the corresponding Notion page. Notion-side cleanup is manual by design.
