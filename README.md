# Obsynx

Obsynx is a two-way sync tool that keeps your Obsidian vault and Notion workspace in sync. Notes saved in Obsidian push to Notion automatically. Notes created or edited in Notion pull back to your vault on demand. Images sync in both directions.

---

## Requirements

- Python 3.10+
- Notion integration token from notion.com/my-integrations
- Cloudinary account
- Debian or Ubuntu Linux

---

## Installation

```bash
git clone https://github.com/Leozist/obsynx.git
cd obsynx
chmod +x install.sh
./install.sh
```

The installer handles dependencies, config, the `obsynx` command, and the file watcher. Open a new terminal when it finishes.

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

## Features

**File watcher** Pushes saved markdown files to Notion within seconds. Runs as a systemd service or screen session.

**Image sync** uploads local images to Cloudinary once and caches the URLs. Images pasted into Notion are downloaded to your vault on pull.

**Conflict resolution** checks size first. Larger file wins. If sizes are close, newer timestamp wins.

**Rolling backups** run before every pull. You set the limit at install and old backups rotate out automatically.

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
    backups/
        vault_YYYYMMDD_HHMMSS/
```

---

## Watcher

**systemd:**
```bash
systemctl --user status obsynx-watcher
systemctl --user restart obsynx-watcher
```

**screen:**
```bash
screen -r obsynx-watcher
```

---
