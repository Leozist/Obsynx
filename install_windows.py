#!/usr/bin/env python3
"""
Obsynx — Windows Installer
Installs Obsynx natively on Windows using Python.
No WSL required.

Run with: python install.py
"""

import os
import sys
import json
import shutil
import hashlib
import subprocess
import winreg
from pathlib import Path
from getpass import getpass

INSTALL_DIR = Path.home() / ".obsidian-sync"
CONFIG_FILE = INSTALL_DIR / "config.json"
LOG_DIR     = INSTALL_DIR / "logs"
SCRIPT_DIR  = Path(__file__).parent.resolve()

# ── Colors (Windows ANSI via colorama or fallback) ─────────────────
try:
    import colorama
    colorama.init()
    RED    = '\033[0;31m'
    GREEN  = '\033[0;32m'
    YELLOW = '\033[1;33m'
    CYAN   = '\033[0;36m'
    BOLD   = '\033[1m'
    NC     = '\033[0m'
except ImportError:
    RED = GREEN = YELLOW = CYAN = BOLD = NC = ""

def banner():
    print(f"{CYAN}{BOLD}")
    print(" ██████╗ ██████╗ ███████╗██╗   ██╗███╗   ██╗██╗  ██╗")
    print("██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝████╗  ██║╚██╗██╔╝")
    print("██║   ██║██████╔╝███████╗ ╚████╔╝ ██╔██╗ ██║ ╚███╔╝ ")
    print("██║   ██║██╔══██╗╚════██║  ╚██╔╝  ██║╚██╗██║ ██╔██╗ ")
    print("╚██████╔╝██████╔╝███████║   ██║   ██║ ╚████║██╔╝ ██╗")
    print(" ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝")
    print(f"{NC}")
    print(f"{BOLD}         Obsidian ↔ Notion Sync Tool — Windows Installer{NC}")
    print()

def step(msg):   print(f"\n{CYAN}{BOLD}▶ {msg}{NC}")
def ok(msg):     print(f"{GREEN}  ✓ {msg}{NC}")
def warn(msg):   print(f"{YELLOW}  ⚠ {msg}{NC}")
def err(msg):    print(f"{RED}  ✗ {msg}{NC}")

def ask(prompt, default=""):
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val or default
    return input(f"  {prompt}: ").strip()

def ask_secret(prompt):
    return getpass(f"  {prompt}: ")

# ── Main menu ──────────────────────────────────────────────────────
def main_menu():
    step("What would you like to do?")
    print()
    print(f"  [1] {CYAN}Fresh install{NC}")
    print(f"  [2] {CYAN}Reconfigure{NC}       — Update individual settings")
    print(f"  [3] {CYAN}Verify API keys{NC}   — Test Notion and Cloudinary connections")
    print(f"  [4] {CYAN}Uninstall{NC}         — Remove Obsynx from this machine")
    print()
    while True:
        choice = input("  Enter 1, 2, 3, or 4: ").strip()
        if choice in ("1", "2", "3", "4"):
            return choice
        print(f"  {RED}Invalid choice.{NC}")

# ── Dependencies ───────────────────────────────────────────────────
def check_deps():
    step("Checking dependencies")

    # Python version
    if sys.version_info < (3, 10):
        err(f"Python 3.10+ required. You have {sys.version}")
        sys.exit(1)
    ok(f"Python {sys.version.split()[0]}")

    # pip packages
    for pkg in ["requests", "watchdog", "colorama"]:
        try:
            __import__(pkg)
            ok(f"{pkg} found")
        except ImportError:
            warn(f"{pkg} not found — installing")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"])
            ok(f"{pkg} installed")

# ── Collect config ─────────────────────────────────────────────────
def collect_config():
    step("Configuration")
    print()

    print(f"  {BOLD}── Notion ──────────────────────────────────{NC}")
    notion_key  = ask_secret("Notion API key")
    notion_page = ask("Notion root page ID")

    print()
    print(f"  {BOLD}── Cloudinary ──────────────────────────────{NC}")
    cloud_name   = ask("Cloud name")
    cloud_key    = ask_secret("API key")
    cloud_secret = ask_secret("API secret")

    print()
    print(f"  {BOLD}── Obsidian Vault ──────────────────────────{NC}")
    default_vault = str(Path.home() / "Documents" / "ObsidianVault")
    vault_path = ask("Full vault path", default_vault)
    vault_path = Path(vault_path)

    if not vault_path.exists():
        err(f"Vault not found: {vault_path}")
        sys.exit(1)
    ok("Vault found")

    print()
    print(f"  {BOLD}── Image Folders ───────────────────────────{NC}")
    print(f"  {YELLOW}Comma-separated paths relative to vault root{NC}")
    print(f"  {YELLOW}Example: Screenshots,Attachments/Images{NC}")
    image_folders = ask("Image folder paths")

    print()
    print(f"  {BOLD}── Backups ─────────────────────────────────{NC}")
    max_backups  = ask("Max backups to keep", "3")
    backup_path  = ask("Backup storage path", str(INSTALL_DIR / "backups"))

    print()
    print(f"  {BOLD}── File Watcher ────────────────────────────{NC}")
    print(f"  {YELLOW}Monitors your vault and auto-pushes to Notion on save{NC}")
    print(f"  {YELLOW}On Windows the watcher runs via Task Scheduler on login{NC}")
    print()

    return {
        "notion_api_key":      notion_key,
        "notion_root_page_id": notion_page,
        "cloudinary_cloud":    cloud_name,
        "cloudinary_api_key":  cloud_key,
        "cloudinary_secret":   cloud_secret,
        "vault_path":          str(vault_path),
        "image_folders":       [f.strip() for f in image_folders.split(",")],
        "backup_path":         backup_path,
        "max_backups":         int(max_backups),
        "watcher_mode":        "task_scheduler",
        "os_mode":             "windows",
        "install_dir":         str(INSTALL_DIR),
    }

# ── Write config ───────────────────────────────────────────────────
def write_config(cfg):
    step("Writing config")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    Path(cfg["backup_path"]).mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

    # Windows ACL — restrict to current user only
    try:
        import subprocess
        subprocess.run(
            ["icacls", str(CONFIG_FILE), "/inheritance:r",
             "/grant:r", f"{os.environ['USERNAME']}:F"],
            capture_output=True
        )
        ok("Config saved (permissions: owner-only)")
    except Exception:
        ok("Config saved")

# ── Install scripts ────────────────────────────────────────────────
def install_scripts():
    step("Installing Obsynx scripts")

    files = [
        "cli.py",
        "sync_utils.py",
        "obsidian_to_notion.py",
        "notion_to_obsidian.py",
        "watcher.py",
    ]

    for f in files:
        src = SCRIPT_DIR / f
        if not src.exists():
            err(f"Missing: {f} — all Obsynx files must be in the same folder as install.py")
            sys.exit(1)
        shutil.copy(src, INSTALL_DIR / f)
        ok(f)

# ── Install obsynx command ─────────────────────────────────────────
def install_command():
    step("Installing 'obsynx' command")

    # Create a .bat launcher in a folder we'll add to PATH
    bin_dir     = INSTALL_DIR / "bin"
    bin_dir.mkdir(exist_ok=True)
    launcher    = bin_dir / "obsynx.bat"

    launcher.write_text(
        f'@echo off\n'
        f'python "{INSTALL_DIR / "cli.py"}" %*\n'
    )
    ok(f"Launcher created: {launcher}")

    # Add bin_dir to user PATH via registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0, winreg.KEY_READ | winreg.KEY_WRITE
        )
        try:
            current_path, _ = winreg.QueryValueEx(key, "PATH")
        except FileNotFoundError:
            current_path = ""

        bin_str = str(bin_dir)
        if bin_str not in current_path:
            new_path = f"{current_path};{bin_str}" if current_path else bin_str
            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
            ok("Added to user PATH (restart terminal to activate)")
        else:
            ok("Already in PATH")

        winreg.CloseKey(key)

        # Broadcast environment change so new terminals pick it up
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
        )
    except Exception as e:
        warn(f"Could not update PATH automatically: {e}")
        warn(f"Manually add to PATH: {bin_dir}")

# ── Setup watcher via Task Scheduler ──────────────────────────────
def setup_watcher():
    step("Setting up file watcher (Task Scheduler)")

    watcher_script = INSTALL_DIR / "watcher.py"
    task_name      = "ObsynxWatcher"
    log_file       = LOG_DIR / "watcher.log"

    # Build the scheduled task using schtasks
    cmd = [
        "schtasks", "/create", "/f",
        "/tn", task_name,
        "/tr", f'python "{watcher_script}"',
        "/sc", "ONLOGON",
        "/rl", "HIGHEST",
        "/it",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            ok(f"Task Scheduler task '{task_name}' created (runs on login)")
        else:
            warn(f"Task Scheduler returned: {result.stderr.strip()}")
            warn("You can create the task manually in Task Scheduler")
    except FileNotFoundError:
        warn("schtasks not found — skipping Task Scheduler setup")
        warn(f"To start watcher manually: python {watcher_script}")
        return

    # Start the watcher now without waiting for next login
    try:
        subprocess.Popen(
            [sys.executable, str(watcher_script)],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=open(log_file, "a"),
            stderr=subprocess.STDOUT,
        )
        ok("Watcher started in background")
    except Exception as e:
        warn(f"Could not start watcher now: {e}")
        warn("It will start automatically on next login")

# ── Reconfigure ────────────────────────────────────────────────────
def run_reconfig():
    if not CONFIG_FILE.exists():
        err("No config found. Run a fresh install first.")
        sys.exit(1)

    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    step("Reconfigure — select field to update")
    fields = {
        "1":  ("notion_api_key",      "Notion API key",         True),
        "2":  ("notion_root_page_id", "Notion root page ID",    False),
        "3":  ("cloudinary_cloud",    "Cloudinary cloud name",  False),
        "4":  ("cloudinary_api_key",  "Cloudinary API key",     True),
        "5":  ("cloudinary_secret",   "Cloudinary API secret",  True),
        "6":  ("vault_path",          "Vault path",             False),
        "7":  ("image_folders",       "Image folders",          False),
        "8":  ("max_backups",         "Max backups",            False),
        "9":  ("backup_path",         "Backup storage path",    False),
    }

    print()
    for num, (_, label, _) in fields.items():
        print(f"  [{num}]  {label}")
    print(f"  [0]  Done")
    print()

    while True:
        choice = input("  Select field to update [0 to finish]: ").strip()
        if choice == "0":
            break
        if choice not in fields:
            print(f"  {RED}Invalid choice.{NC}")
            continue

        key, label, secret = fields[choice]

        if choice == "7":
            print(f"  {YELLOW}Comma-separated paths relative to vault root{NC}")
            val = ask(f"New {label}")
            cfg[key] = [x.strip() for x in val.split(",")]
        elif choice == "8":
            val = ask(f"New {label}", str(cfg.get(key, 3)))
            cfg[key] = int(val)
        elif choice == "6":
            val = ask(f"New {label}", cfg.get(key, ""))
            if not Path(val).exists():
                err(f"Path not found: {val}")
                continue
            cfg[key] = val
        elif secret:
            val = ask_secret(f"New {label}")
            cfg[key] = val
        else:
            val = ask(f"New {label}", cfg.get(key, ""))
            cfg[key] = val

        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=4)
        ok(f"{label} updated")
        print()

    ok("Reconfiguration complete")

# ── Verify API keys ────────────────────────────────────────────────
def run_verify():
    if not CONFIG_FILE.exists():
        err("No config found. Run a fresh install first.")
        sys.exit(1)

    step("Verifying API connections")
    print()

    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    try:
        import requests
    except ImportError:
        err("requests not installed: pip install requests")
        sys.exit(1)

    # Notion key
    print("  Notion API key...")
    try:
        r = requests.get(
            "https://api.notion.com/v1/users/me",
            headers={
                "Authorization": f"Bearer {cfg['notion_api_key']}",
                "Notion-Version": "2022-06-28"
            },
            timeout=10
        )
        if r.status_code == 200:
            ok("Notion API key valid")
        elif r.status_code == 401:
            err("Notion API key invalid or expired")
        else:
            warn(f"Notion returned {r.status_code}")
    except Exception as e:
        err(f"Notion connection failed: {e}")

    # Notion page
    print("  Notion root page...")
    try:
        page_id = cfg["notion_root_page_id"].replace("-", "")
        r = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers={
                "Authorization": f"Bearer {cfg['notion_api_key']}",
                "Notion-Version": "2022-06-28"
            },
            timeout=10
        )
        if r.status_code == 200:
            ok("Notion root page accessible")
        elif r.status_code == 404:
            err("Page not found — check page ID and integration connection")
        elif r.status_code == 403:
            err("Page access denied — connect your integration to the page")
        else:
            warn(f"Notion page returned {r.status_code}")
    except Exception as e:
        err(f"Notion page check failed: {e}")

    # Cloudinary
    print("  Cloudinary...")
    try:
        import time
        ts  = str(int(time.time()))
        sig = hashlib.sha1(
            f"timestamp={ts}{cfg['cloudinary_secret']}".encode()
        ).hexdigest()
        r = requests.get(
            f"https://api.cloudinary.com/v1_1/{cfg['cloudinary_cloud']}/usage",
            params={
                "api_key":   cfg["cloudinary_api_key"],
                "timestamp": ts,
                "signature": sig,
            },
            timeout=10
        )
        if r.status_code == 200:
            ok("Cloudinary credentials valid")
        elif r.status_code == 401:
            err("Cloudinary credentials invalid")
        else:
            warn(f"Cloudinary returned {r.status_code}")
    except Exception as e:
        err(f"Cloudinary connection failed: {e}")

    # Vault
    print("  Vault path...")
    vault = Path(cfg["vault_path"])
    if vault.exists():
        ok("Vault found")
    else:
        err(f"Vault not found: {vault}")

    print()

# ── Summary ────────────────────────────────────────────────────────
def print_summary():
    print()
    print(f"{GREEN}{BOLD}╔══════════════════════════════════════════════════════════════╗{NC}")
    print(f"{GREEN}{BOLD}║               Obsynx Installation Complete!                 ║{NC}")
    print(f"{GREEN}{BOLD}╚══════════════════════════════════════════════════════════════╝{NC}")
    print()
    print(f"  {BOLD}Platform : {CYAN}Windows{NC}")
    print()
    print(f"  {BOLD}Commands:{NC}")
    print(f"  {CYAN}obsynx push{NC}     — Upload vault → Notion")
    print(f"  {CYAN}obsynx pull{NC}     — Backup then pull Notion → Obsidian")
    print(f"  {CYAN}obsynx status{NC}   — Sync state, backups, logs")
    print(f"  {CYAN}obsynx restore{NC}  — Pick and restore a backup")
    print(f"  {CYAN}obsynx help{NC}     — Show all commands")
    print()
    print(f"  {BOLD}Watcher:{NC}")
    print(f"  Running via Task Scheduler (auto-starts on login)")
    print(f"  Manage in Task Scheduler under: ObsynxWatcher")
    print()
    print(f"  {BOLD}Paths:{NC}")
    print(f"  Config  : {CYAN}{CONFIG_FILE}{NC}")
    print(f"  Logs    : {CYAN}{LOG_DIR}{NC}")
    print()
    print(f"  {YELLOW}⚠  Open a new terminal to activate the obsynx command{NC}")
    print()

# ── Uninstall ──────────────────────────────────────────────────────
def run_uninstall():
    step("Uninstall Obsynx")
    print()
    print(f"  {YELLOW}This will remove:{NC}")
    print(f"  • All Obsynx scripts in {INSTALL_DIR}")
    print(f"  • The obsynx command launcher")
    print(f"  • Config, logs, and state files")
    print(f"  • Task Scheduler watcher task")
    print(f"  • PATH registry entry")
    print()
    print(f"  {YELLOW}This will NOT remove:{NC}")
    print(f"  • Your Obsidian vault")
    print(f"  • Your Notion pages")
    print(f"  • Your Cloudinary images")
    print(f"  • Your backups (preserved separately)")
    print()
    confirm = input("  Type 'yes' to confirm uninstall: ").strip()
    if confirm.lower() != "yes":
        print("  Cancelled.")
        return

    print()

    # Stop and remove Task Scheduler task
    try:
        result = subprocess.run(
            ["schtasks", "/delete", "/tn", "ObsynxWatcher", "/f"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            ok("Task Scheduler task removed")
        else:
            warn("Could not remove Task Scheduler task — remove manually if needed")
    except FileNotFoundError:
        pass

    # Kill running watcher process
    try:
        subprocess.run(
            ["taskkill", "/f", "/fi", "WINDOWTITLE eq ObsynxWatcher"],
            capture_output=True
        )
    except Exception:
        pass

    # Preserve backups before removing install dir
    backup_dir = INSTALL_DIR / "backups"
    preserved  = Path.home() / ".obsynx-backups"
    if backup_dir.exists():
        preserved.mkdir(exist_ok=True)
        for item in backup_dir.iterdir():
            shutil.move(str(item), str(preserved / item.name))
        warn(f"Backups preserved at: {preserved}")

    # Remove install dir
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR)
        ok("Scripts and config removed")

    # Remove bin dir and launcher
    bin_dir = INSTALL_DIR / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
        ok("Launcher removed")

    # Remove from user PATH registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0, winreg.KEY_READ | winreg.KEY_WRITE
        )
        try:
            current_path, reg_type = winreg.QueryValueEx(key, "PATH")
            bin_str  = str(INSTALL_DIR / "bin")
            new_path = ";".join(
                p for p in current_path.split(";") if p != bin_str
            )
            winreg.SetValueEx(key, "PATH", 0, reg_type, new_path)
            ok("Removed from PATH")
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
    except Exception as e:
        warn(f"Could not clean PATH: {e}")

    print()
    print(f"{GREEN}{BOLD}  Obsynx uninstalled successfully.{NC}")
    print(f"  Open a new terminal to finish cleaning your environment.")
    print()


# ── Entry point ────────────────────────────────────────────────────
def main():
    if sys.platform != "win32":
        print("This installer is for Windows only.")
        print("On Linux run: bash install.sh")
        sys.exit(1)

    banner()
    choice = main_menu()

    if choice == "1":
        check_deps()
        cfg = collect_config()
        write_config(cfg)
        install_scripts()
        install_command()
        setup_watcher()
        print_summary()
    elif choice == "2":
        run_reconfig()
    elif choice == "3":
        run_verify()
    elif choice == "4":
        run_uninstall()

if __name__ == "__main__":
    main()
