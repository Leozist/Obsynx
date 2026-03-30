#!/usr/bin/env python3
"""
sync_utils.py — Shared utilities for Obsynx
Handles: config loading, rolling backups, logging, status reporting
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────
INSTALL_DIR = Path.home() / ".obsidian-sync"
CONFIG_FILE = INSTALL_DIR / "config.json"
LOG_FILE    = INSTALL_DIR / "logs" / "sync.log"
STATE_FILE  = INSTALL_DIR / "push_state.json"
PULL_STATE  = INSTALL_DIR / "pull_state.json"
IMG_CACHE   = INSTALL_DIR / "img_cache.json"

# ── Config ─────────────────────────────────────────────────────────
def load_config():
    if not CONFIG_FILE.exists():
        print("❌  Config not found. Run install.sh first.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        cfg = json.load(f)
    cfg["vault_path"]         = Path(cfg["vault_path"])
    cfg["backup_path"]        = Path(cfg["backup_path"])
    cfg["install_dir"]        = Path(cfg["install_dir"])
    cfg["image_folder_paths"] = [
        cfg["vault_path"] / folder
        for folder in cfg.get("image_folders", [])
    ]
    return cfg

# ── Logging ────────────────────────────────────────────────────────
def setup_logger(name="obsynx"):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)
        fh = logging.FileHandler(LOG_FILE)
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
    return logger

# ── JSON helpers ───────────────────────────────────────────────────
def load_json(path):
    path = Path(path)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── Rolling Backup ─────────────────────────────────────────────────
def create_backup(cfg, logger=None):
    """
    Create a timestamped backup of the vault.
    Keeps only the last N backups (cfg max_backups).
    """
    vault_path  = cfg["vault_path"]
    backup_base = cfg["backup_path"]
    max_backups = int(cfg.get("max_backups", 3))
    log         = logger.info if logger else print

    backup_base.mkdir(parents=True, exist_ok=True)
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dest = backup_base / f"vault_{timestamp}"

    log(f"\n💾 Creating backup → {backup_dest.name}")
    try:
        shutil.copytree(
            vault_path,
            backup_dest,
            ignore=shutil.ignore_patterns(".git", ".obsidian", ".trash")
        )
        log(f"   ✓ Backup complete")
    except Exception as e:
        log(f"   ✗ Backup failed: {e}")
        return None

    # Prune old backups — keep newest N
    existing = sorted(
        backup_base.glob("vault_*"),
        key=lambda p: p.stat().st_mtime
    )
    while len(existing) > max_backups:
        oldest = existing.pop(0)
        try:
            shutil.rmtree(oldest)
            log(f"   🗑  Removed old backup: {oldest.name}")
        except Exception as e:
            log(f"   ⚠  Could not remove {oldest.name}: {e}")

    log(f"   📦 Backups kept: {min(len(existing) + 1, max_backups)}/{max_backups}\n")
    return backup_dest

def list_backups(cfg):
    backup_base = cfg["backup_path"]
    if not backup_base.exists():
        return []
    return sorted(
        backup_base.glob("vault_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

# ── Restore ────────────────────────────────────────────────────────
def restore_backup(cfg, logger=None):
    log     = logger.info if logger else print
    backups = list_backups(cfg)

    if not backups:
        log("❌  No backups found.")
        return

    log("\n📦 Available backups:\n")
    for i, b in enumerate(backups):
        size = sum(f.stat().st_size for f in b.rglob("*") if f.is_file())
        ts   = b.name.replace("vault_", "").replace("_", " ")
        log(f"  [{i+1}] {ts}  ({size // 1024 // 1024} MB)")

    print("")
    choice = input("  Select backup to restore [1]: ").strip() or "1"
    try:
        selected = backups[int(choice) - 1]
    except (ValueError, IndexError):
        log("❌  Invalid selection.")
        return

    vault_path = cfg["vault_path"]
    print(f"\n  ⚠  This will REPLACE:\n     {vault_path}")
    print(f"  With backup:\n     {selected.name}\n")
    confirm = input("  Type 'yes' to confirm: ").strip()
    if confirm.lower() != "yes":
        log("   Cancelled.")
        return

    log(f"\n   Restoring {selected.name} ...")
    try:
        if vault_path.exists():
            shutil.rmtree(vault_path)
        shutil.copytree(selected, vault_path)
        log("   ✓ Restore complete")
    except Exception as e:
        log(f"   ✗ Restore failed: {e}")

# ── Status ─────────────────────────────────────────────────────────
def print_status(cfg):
    push_state = load_json(STATE_FILE)
    pull_state = load_json(PULL_STATE)
    img_cache  = load_json(IMG_CACHE)
    backups    = list_backups(cfg)

    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Obsynx — Sync Status")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Vault        : {cfg['vault_path']}")
    print(f"  Notion page  : {cfg['notion_root_page_id']}")
    print(f"  Cloudinary   : {cfg['cloudinary_cloud']}")
    print()
    print(f"  Push tracked : {len(push_state)} files")
    print(f"  Pull tracked : {len(pull_state)} pages")
    print(f"  Image cache  : {len(img_cache)} images on Cloudinary")
    print()
    print(f"  Backups ({len(backups)}/{cfg.get('max_backups', 3)}):")
    for b in backups:
        size = sum(f.stat().st_size for f in b.rglob("*") if f.is_file())
        ts   = b.name.replace("vault_", "").replace("_", " ")
        print(f"    • {ts}  ({size // 1024 // 1024} MB)")
    if not backups:
        print("    • No backups yet — run 'obsynx pull' to create one")
    print()

    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().strip().split("\n")
        recent = lines[-8:] if len(lines) >= 8 else lines
        print("  Recent activity:")
        for line in recent:
            print(f"    {line}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

# ── CLI ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = load_config()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print_status(cfg)
    elif cmd == "restore":
        restore_backup(cfg)
    elif cmd == "backup":
        create_backup(cfg)
    else:
        print(f"Unknown: {cmd}")
