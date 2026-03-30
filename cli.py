#!/usr/bin/env python3
"""
Obsynx — Obsidian ↔ Notion Sync Tool
Usage: obsynx [push|pull|status|restore|help]
"""

import sys
from pathlib import Path

BANNER = """
 ██████╗ ██████╗ ███████╗██╗   ██╗███╗   ██╗██╗  ██╗
██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝████╗  ██║╚██╗██╔╝
██║   ██║██████╔╝███████╗ ╚████╔╝ ██╔██╗ ██║ ╚███╔╝ 
██║   ██║██╔══██╗╚════██║  ╚██╔╝  ██║╚██╗██║ ██╔██╗ 
╚██████╔╝██████╔╝███████║   ██║   ██║ ╚████║██╔╝ ██╗
 ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝
         Obsidian ↔ Notion Sync Tool v1.0
"""

HELP_TEXT = """
Usage: obsynx <command>

Commands:
  push      Upload your Obsidian vault to Notion
            Images are uploaded to Cloudinary automatically
            Only changed files are pushed (state tracked)

  pull      Pull Notion pages back to Obsidian
            Always creates a rolling backup first
            Latest content wins on conflict (size + timestamp)

  status    Show sync state, backup list, image cache,
            and recent log entries

  restore   Interactively pick and restore a vault backup
            Lists available backups with size and date

  help      Show this help message

Examples:
  obsynx push
  obsynx pull
  obsynx status
  obsynx restore

Config:   ~/.obsidian-sync/config.json
Logs:     ~/.obsidian-sync/logs/sync.log
Backups:  ~/.obsidian-sync/backups/
"""

def cmd_push():
    from obsidian_to_notion import upload_vault
    upload_vault()

def cmd_pull():
    from notion_to_obsidian import pull
    pull()

def cmd_status():
    from sync_utils import load_config, print_status
    cfg = load_config()
    print_status(cfg)

def cmd_restore():
    from sync_utils import load_config, restore_backup
    cfg = load_config()
    restore_backup(cfg)

def cmd_help():
    print(BANNER)
    print(HELP_TEXT)

COMMANDS = {
    "push":    cmd_push,
    "pull":    cmd_pull,
    "status":  cmd_status,
    "restore": cmd_restore,
    "help":    cmd_help,
}

def main():
    # Add install dir to path so all modules resolve
    install_dir = Path.home() / ".obsidian-sync"
    sys.path.insert(0, str(install_dir))

    if len(sys.argv) < 2:
        print(BANNER)
        print("  Run 'obsynx help' for usage.\n")
        sys.exit(0)

    command = sys.argv[1].lower()

    if command not in COMMANDS:
        print(f"\n  ✗ Unknown command: '{command}'")
        print(f"  Run 'obsynx help' to see available commands.\n")
        sys.exit(1)

    COMMANDS[command]()

if __name__ == "__main__":
    main()
