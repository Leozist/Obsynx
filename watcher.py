#!/usr/bin/env python3
"""
watcher.py — Obsynx vault file watcher
Monitors your Obsidian vault for .md file saves and auto-pushes to Notion.
Configured and started automatically by install.sh.
"""

import sys
import time
import threading
import requests
from pathlib import Path
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("❌  watchdog not installed: pip install watchdog --break-system-packages")
    sys.exit(1)

sys.path.insert(0, str(Path.home() / ".obsidian-sync"))
from sync_utils import load_config, setup_logger, load_json, save_json

cfg    = load_config()
logger = setup_logger("obsynx-watcher")

VAULT_PATH   = cfg["vault_path"]
SKIP_DIRS    = {".obsidian", ".trash", ".git"}
DEBOUNCE_SEC = 3.0  # seconds after last save before pushing

pending       = {}
pending_lock  = threading.Lock()

# ── Notion headers ─────────────────────────────────────────────────
HEADERS = {
    "Authorization": f"Bearer {cfg['notion_api_key']}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

STATE_FILE = Path.home() / ".obsidian-sync" / "push_state.json"
IMG_CACHE  = Path.home() / ".obsidian-sync" / "img_cache.json"

# ── Event handler ──────────────────────────────────────────────────
class VaultHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if not event.is_directory:
            self._queue(Path(event.src_path))

    def on_created(self, event):
        if not event.is_directory:
            self._queue(Path(event.src_path))

    def _queue(self, path):
        if path.suffix != ".md":
            return
        for part in path.parts:
            if part in SKIP_DIRS:
                return
        with pending_lock:
            pending[str(path)] = time.time()

# ── Debounce worker ────────────────────────────────────────────────
def debounce_worker():
    while True:
        time.sleep(1.0)
        now = time.time()
        with pending_lock:
            ready = [p for p, t in pending.items() if now - t >= DEBOUNCE_SEC]
            for p in ready:
                del pending[p]
        for p in ready:
            push_file(Path(p))

# ── Push single file ───────────────────────────────────────────────
def push_file(path):
    from obsidian_to_notion import md_to_notion_blocks, create_notion_page, append_blocks

    if not path.exists():
        return

    rel   = str(path.relative_to(VAULT_PATH))
    state = load_json(STATE_FILE)
    mtime = path.stat().st_mtime

    if state.get(rel) == mtime:
        return  # Unchanged since last push

    logger.info(f"📤 {rel}")
    img_cache = load_json(IMG_CACHE)

    try:
        content  = path.read_text(encoding="utf-8", errors="ignore")
        blocks   = md_to_notion_blocks(content, img_cache)
        parent_id = resolve_parent(path, state)

        if not parent_id:
            logger.info(f"   ✗ Could not resolve parent page")
            return

        page_id = create_notion_page(parent_id, path.stem, blocks[:100])
        if len(blocks) > 100:
            append_blocks(page_id, blocks[100:])

        state[rel] = mtime
        save_json(STATE_FILE, state)
        logger.info(f"   ✓ Pushed")

    except Exception as e:
        logger.info(f"   ✗ {e}")

def resolve_parent(file_path, state):
    """Walk folder path, creating Notion folder pages as needed."""
    ROOT = cfg["notion_root_page_id"]
    parts = list(file_path.relative_to(VAULT_PATH).parts[:-1])

    if not parts:
        return ROOT

    parent_id = ROOT
    for part in parts:
        cache_key = f"__folder__{parent_id}/{part}"
        if cache_key in state:
            parent_id = state[cache_key]
            continue
        try:
            r = requests.post(
                "https://api.notion.com/v1/pages",
                headers=HEADERS,
                json={
                    "parent": {"page_id": parent_id},
                    "properties": {
                        "title": {"title": [{"type": "text", "text": {"content": part}}]}
                    }
                }
            )
            r.raise_for_status()
            new_id = r.json()["id"]
            state[cache_key] = new_id
            save_json(STATE_FILE, state)
            parent_id = new_id
            time.sleep(0.3)
        except Exception as e:
            logger.info(f"   ✗ Folder '{part}': {e}")
            return None

    return parent_id

# ── Main ───────────────────────────────────────────────────────────
def main():
    if not VAULT_PATH.exists():
        logger.info(f"❌  Vault not found: {VAULT_PATH}")
        sys.exit(1)

    logger.info(f"\n👁  Obsynx Watcher started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   Vault    : {VAULT_PATH}")
    logger.info(f"   Debounce : {DEBOUNCE_SEC}s after save\n")

    threading.Thread(target=debounce_worker, daemon=True).start()

    observer = Observer()
    observer.schedule(VaultHandler(), str(VAULT_PATH), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n👋 Watcher stopped")
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
