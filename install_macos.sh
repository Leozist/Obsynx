#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║              Obsynx — macOS Installer                        ║
# ║          Obsidian ↔ Notion Sync Tool Setup                  ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

INSTALL_DIR="$HOME/.obsidian-sync"
CONFIG_FILE="$INSTALL_DIR/config.json"
LOG_DIR="$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_PATH="$HOME/.local/bin/obsynx"
PLIST_PATH="$HOME/Library/LaunchAgents/com.obsynx.watcher.plist"
WATCHER_MODE=""
AUTOMATE="n"

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo " ██████╗ ██████╗ ███████╗██╗   ██╗███╗   ██╗██╗  ██╗"
    echo "██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝████╗  ██║╚██╗██╔╝"
    echo "██║   ██║██████╔╝███████╗ ╚████╔╝ ██╔██╗ ██║ ╚███╔╝ "
    echo "██║   ██║██╔══██╗╚════██║  ╚██╔╝  ██║╚██╗██║ ██╔██╗ "
    echo "╚██████╔╝██████╔╝███████║   ██║   ██║ ╚████║██╔╝ ██╗"
    echo " ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═══╝╚═╝  ╚═╝"
    echo -e "${NC}"
    echo -e "${BOLD}         Obsidian ↔ Notion Sync Tool — macOS Installer${NC}"
    echo ""
}

print_step() { echo -e "\n${CYAN}${BOLD}▶ $1${NC}"; }
print_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
print_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
print_err()  { echo -e "${RED}  ✗ $1${NC}"; }

ask() {
    local prompt="$1" default="$2" result
    if [ -n "$default" ]; then
        read -rp "  $prompt [$default]: " result
        echo "${result:-$default}"
    else
        read -rp "  $prompt: " result
        echo "$result"
    fi
}

ask_secret() {
    local prompt="$1" result
    read -rsp "  $prompt: " result
    echo "" >&2
    echo "$result"
}

# macOS's BSD sed requires an explicit (empty) backup extension for -i.
sed_inplace() {
    sed -i '' "$@"
}

# Terminal.app launches a login shell: bash reads .bash_profile, not
# .bashrc, on macOS. zsh has been the default shell since Catalina.
detect_rc_file() {
    case "$SHELL" in
        */zsh)
            echo "$HOME/.zshrc"
            ;;
        */bash)
            if [ -f "$HOME/.bash_profile" ]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        *)
            echo "$HOME/.zshrc"
            ;;
    esac
}

# ── Main menu ──────────────────────────────────────────────────────
main_menu() {
    print_step "What would you like to do?"
    echo ""
    echo -e "  [1] ${CYAN}Fresh install${NC}"
    echo -e "  [2] ${CYAN}Reconfigure${NC}       — Update individual settings"
    echo -e "  [3] ${CYAN}Verify API keys${NC}   — Test Notion and Cloudinary connections"
    echo -e "  [4] ${CYAN}Uninstall${NC}         — Remove Obsynx from this machine"
    echo ""

    while true; do
        read -rp "  Enter 1, 2, 3, or 4: " choice
        case "$choice" in
            1) MODE="install";    break ;;
            2) MODE="reconfig";   break ;;
            3) MODE="verify";     break ;;
            4) MODE="uninstall";  break ;;
            *) echo -e "  ${RED}Invalid choice.${NC}" ;;
        esac
    done
}

# ── Dependencies ───────────────────────────────────────────────────
install_pip_pkg() {
    local pkg="$1"
    if python3 -c "import $pkg" 2>/dev/null; then
        print_ok "$pkg found"
        return
    fi
    print_warn "$pkg not found — installing"
    if pip3 install --user "$pkg" -q 2>/dev/null; then
        print_ok "$pkg installed"
    elif pip3 install --user --break-system-packages "$pkg" -q 2>/dev/null; then
        print_ok "$pkg installed"
    else
        print_err "Could not install $pkg automatically — run: pip3 install --user $pkg"
        exit 1
    fi
}

check_deps() {
    print_step "Checking dependencies"

    if ! command -v python3 &>/dev/null; then
        print_err "python3 not found."
        echo -e "  ${YELLOW}Install it via: brew install python3${NC}"
        echo -e "  ${YELLOW}or from: https://python.org/downloads${NC}"
        exit 1
    fi
    print_ok "python3 $(python3 --version | cut -d' ' -f2)"

    if ! command -v pip3 &>/dev/null; then
        print_err "pip3 not found alongside python3 — reinstall Python."
        exit 1
    fi

    install_pip_pkg requests
    install_pip_pkg watchdog

    if ! command -v screen &>/dev/null; then
        print_warn "screen not found (unusual on macOS)"
        print_warn "If you plan to use screen-mode watcher, run: brew install screen"
    else
        print_ok "screen found"
    fi
}

# ── Collect config ─────────────────────────────────────────────────
collect_config() {
    print_step "Configuration"
    echo ""

    echo -e "  ${BOLD}── Notion ──────────────────────────────────${NC}"
    NOTION_KEY=$(ask_secret "Notion API key")
    NOTION_PAGE=$(ask "Notion root page ID")

    echo ""
    echo -e "  ${BOLD}── Cloudinary ──────────────────────────────${NC}"
    CLOUDINARY_CLOUD=$(ask "Cloud name")
    CLOUDINARY_KEY=$(ask_secret "API key")
    CLOUDINARY_SECRET=$(ask_secret "API secret")

    echo ""
    echo -e "  ${BOLD}── Obsidian Vault ──────────────────────────${NC}"
    VAULT_PATH=$(ask "Full vault path" "$HOME/Documents/ObsidianVault")
    VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

    if [ ! -d "$VAULT_PATH" ]; then
        print_err "Vault not found: $VAULT_PATH"
        exit 1
    fi
    print_ok "Vault found"

    echo ""
    echo -e "  ${BOLD}── Image Folders ───────────────────────────${NC}"
    echo -e "  ${YELLOW}Comma-separated paths relative to vault root${NC}"
    echo -e "  ${YELLOW}Example: Screenshots,Attachments/Images${NC}"
    IMAGE_FOLDERS=$(ask "Image folder paths")

    echo ""
    echo -e "  ${BOLD}── Backups ─────────────────────────────────${NC}"
    MAX_BACKUPS=$(ask "Max backups to keep" "3")
    BACKUP_PATH=$(ask "Backup storage path" "$INSTALL_DIR/backups")
    BACKUP_PATH="${BACKUP_PATH/#\~/$HOME}"

    echo ""
    echo -e "  ${BOLD}── Automation ───────────────────────────────${NC}"
    echo -e "  ${YELLOW}Obsynx can run a background watcher that auto-pushes${NC}"
    echo -e "  ${YELLOW}saved notes to Notion within seconds. Pulling from Notion${NC}"
    echo -e "  ${YELLOW}always stays manual ('obsynx pull') — Obsynx never${NC}"
    echo -e "  ${YELLOW}auto-pulls, whether or not you enable this.${NC}"
    echo ""
    echo -e "  ${RED}${BOLD}Known risk:${NC} ${YELLOW}earlier versions could lose track of a${NC}"
    echo -e "  ${YELLOW}note's existing Notion page once a folder passed 100 notes,${NC}"
    echo -e "  ${YELLOW}creating a fresh duplicate page on every save instead of${NC}"
    echo -e "  ${YELLOW}updating the old one. This install includes the fix, but${NC}"
    echo -e "  ${YELLOW}automation still means changes go to Notion unattended.${NC}"
    echo ""
    AUTOMATE_RAW=$(ask "Enable auto-push watcher? [y/N]" "n")
    case "$AUTOMATE_RAW" in
        y|Y|yes|YES) AUTOMATE="y" ;;
        *)           AUTOMATE="n" ;;
    esac

    if [ "$AUTOMATE" = "y" ]; then
        echo ""
        echo -e "  Watcher modes:"
        echo -e "    ${CYAN}launchd${NC} — auto-starts on login (recommended)"
        echo -e "    ${CYAN}screen${NC}  — runs in a background screen session"
        echo ""
        WATCHER_MODE=$(ask "Watcher mode [launchd/screen]" "launchd")
    else
        print_ok "Automation disabled — you'll run 'obsynx push' / 'obsynx pull' by hand"
        WATCHER_MODE="none"
    fi
}

# ── Write config ───────────────────────────────────────────────────
write_config() {
    print_step "Writing config"

    mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$BACKUP_PATH"

    IFS=',' read -ra FOLDERS <<< "$IMAGE_FOLDERS"
    FOLDERS_JSON="["
    for i in "${!FOLDERS[@]}"; do
        folder=$(echo "${FOLDERS[$i]}" | xargs)
        FOLDERS_JSON+="\"$folder\""
        [ $i -lt $((${#FOLDERS[@]}-1)) ] && FOLDERS_JSON+=","
    done
    FOLDERS_JSON+="]"

    cat > "$CONFIG_FILE" << EOF
{
    "notion_api_key": "$NOTION_KEY",
    "notion_root_page_id": "$NOTION_PAGE",
    "cloudinary_cloud": "$CLOUDINARY_CLOUD",
    "cloudinary_api_key": "$CLOUDINARY_KEY",
    "cloudinary_secret": "$CLOUDINARY_SECRET",
    "vault_path": "$VAULT_PATH",
    "image_folders": $FOLDERS_JSON,
    "backup_path": "$BACKUP_PATH",
    "max_backups": $MAX_BACKUPS,
    "automation_enabled": $([ "$AUTOMATE" = "y" ] && echo true || echo false),
    "watcher_mode": "$WATCHER_MODE",
    "os_mode": "macos",
    "install_dir": "$INSTALL_DIR"
}
EOF

    chmod 600 "$CONFIG_FILE"
    print_ok "Config saved (permissions: owner-only)"
}

# ── Reconfigure ────────────────────────────────────────────────────
run_reconfig() {
    if [ ! -f "$CONFIG_FILE" ]; then
        print_err "No config found. Run a fresh install first."
        exit 1
    fi

    print_step "Reconfigure"
    echo ""

    RECONFIG_SCRIPT=$(mktemp "${TMPDIR:-/tmp}/obsynx_reconfig_XXXXXX.py")

    cat > "$RECONFIG_SCRIPT" << 'PYEOF'
import json, sys, getpass
from pathlib import Path

CONFIG_FILE = Path(sys.argv[1])
cfg = json.loads(CONFIG_FILE.read_text())

GREEN = "\033[0;32m"
RED   = "\033[0;31m"
YELLOW= "\033[1;33m"
NC    = "\033[0m"

fields = [
    ("notion_api_key",      "Notion API key",        "secret"),
    ("notion_root_page_id", "Notion root page ID",   "text"),
    ("cloudinary_cloud",    "Cloudinary cloud name", "text"),
    ("cloudinary_api_key",  "Cloudinary API key",    "secret"),
    ("cloudinary_secret",   "Cloudinary API secret", "secret"),
    ("vault_path",          "Vault path",            "path"),
    ("image_folders",       "Image folders",         "folders"),
    ("max_backups",         "Max backups",           "int"),
    ("backup_path",         "Backup storage path",   "text"),
]

print()
for i, (_, label, _) in enumerate(fields, 1):
    print(f"  [{i:2}]  {label}")
print(f"  [ 0]  Done")
print()

while True:
    try:
        choice = input("  Select field [0 to finish]: ").strip()
    except (KeyboardInterrupt, EOFError):
        break

    if choice == "0":
        break

    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(fields):
            raise ValueError
    except ValueError:
        print(f"  {RED}Invalid choice.{NC}")
        continue

    key, label, kind = fields[idx]

    try:
        if kind == "secret":
            val = getpass.getpass(f"  New {label}: ")
        elif kind == "path":
            val = input(f"  New {label} [{cfg.get(key,'')}]: ").strip() or cfg.get(key, "")
            val = str(Path(val).expanduser())
            if not Path(val).exists():
                print(f"  {RED}Path not found: {val}{NC}")
                continue
            cfg[key] = val
        elif kind == "folders":
            print(f"  {YELLOW}Comma-separated paths relative to vault root{NC}")
            val = input(f"  New {label}: ").strip()
            cfg[key] = [x.strip() for x in val.split(",")]
        elif kind == "int":
            default = str(cfg.get(key, 3))
            val = input(f"  New {label} [{default}]: ").strip() or default
            cfg[key] = int(val)
        else:
            val = input(f"  New {label} [{cfg.get(key,'')}]: ").strip() or cfg.get(key, "")
            cfg[key] = val

        CONFIG_FILE.write_text(json.dumps(cfg, indent=4))
        print(f"  {GREEN}✓ {label} updated{NC}")

    except (KeyboardInterrupt, EOFError):
        break
    except Exception as e:
        print(f"  {RED}Error: {e}{NC}")

    print()

print(f"  {GREEN}Field reconfiguration complete{NC}")
PYEOF

    python3 "$RECONFIG_SCRIPT" "$CONFIG_FILE"
    rm -f "$RECONFIG_SCRIPT"

    # ── Automation toggle ──
    echo ""
    print_step "Automation"

    CURRENT=$(python3 -c "import json; print('y' if json.loads(open('$CONFIG_FILE').read()).get('automation_enabled') else 'n')")
    CUR_MODE=$(python3 -c "import json; print(json.loads(open('$CONFIG_FILE').read()).get('watcher_mode','none'))")

    if [ "$CURRENT" = "y" ]; then
        echo -e "  Auto-push watcher is currently ${GREEN}ON${NC} (mode: $CUR_MODE)"
    else
        echo -e "  Auto-push watcher is currently ${YELLOW}OFF${NC} — you push/pull manually"
    fi
    echo ""
    echo -e "  ${YELLOW}Reminder: pulling from Notion is always manual, never automatic.${NC}"
    echo ""
    NEW_RAW=$(ask "Enable auto-push watcher? [y/N]" "$CURRENT")
    case "$NEW_RAW" in
        y|Y|yes|YES) NEW="y" ;;
        *)           NEW="n" ;;
    esac

    if [ "$NEW" = "$CURRENT" ] && [ "$NEW" = "y" ]; then
        print_ok "No change — watcher stays on (mode: $CUR_MODE)"
        return
    elif [ "$NEW" = "$CURRENT" ]; then
        print_ok "No change — watcher stays off"
        return
    fi

    if [ "$NEW" = "y" ]; then
        echo ""
        WATCHER_MODE=$(ask "Watcher mode [launchd/screen]" "launchd")
        AUTOMATE="y"
        python3 - "$CONFIG_FILE" "$WATCHER_MODE" << 'PYEOF'
import json, sys
p, mode = sys.argv[1], sys.argv[2]
cfg = json.loads(open(p).read())
cfg["automation_enabled"] = True
cfg["watcher_mode"] = mode
open(p, "w").write(json.dumps(cfg, indent=4))
PYEOF
        setup_watcher
        print_ok "Watcher enabled"
    else
        stop_watcher
        python3 - "$CONFIG_FILE" << 'PYEOF'
import json, sys
p = sys.argv[1]
cfg = json.loads(open(p).read())
cfg["automation_enabled"] = False
cfg["watcher_mode"] = "none"
open(p, "w").write(json.dumps(cfg, indent=4))
PYEOF
        print_ok "Watcher disabled"
    fi
}

# ── Verify API keys ────────────────────────────────────────────────
run_verify() {
    if [ ! -f "$CONFIG_FILE" ]; then
        print_err "No config found. Run a fresh install first."
        exit 1
    fi

    print_step "Verifying API connections"
    echo ""

    python3 << 'PYEOF'
import json, sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".obsidian-sync" / "config.json"

try:
    cfg = json.loads(CONFIG_FILE.read_text())
except Exception as e:
    print(f"  ✗ Could not read config: {e}")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("  ✗ requests not installed: pip3 install --user requests")
    sys.exit(1)

# ── Notion ──
print("  Notion...")
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
        print("  \033[32m✓ Notion API key valid\033[0m")
    elif r.status_code == 401:
        print("  \033[31m✗ Notion API key invalid or expired\033[0m")
    else:
        print(f"  \033[33m⚠ Notion returned {r.status_code}\033[0m")
except Exception as e:
    print(f"  \033[31m✗ Notion connection failed: {e}\033[0m")

# ── Notion page ──
print("  Notion page...")
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
        print("  \033[32m✓ Notion root page accessible\033[0m")
    elif r.status_code == 404:
        print("  \033[31m✗ Notion page not found — check page ID and integration connection\033[0m")
    elif r.status_code == 403:
        print("  \033[31m✗ Notion page access denied — connect your integration to the page\033[0m")
    else:
        print(f"  \033[33m⚠ Notion page returned {r.status_code}\033[0m")
except Exception as e:
    print(f"  \033[31m✗ Notion page check failed: {e}\033[0m")

# ── Cloudinary ──
print("  Cloudinary...")
try:
    import hashlib, time
    ts  = str(int(time.time()))
    sig = hashlib.sha1(f"timestamp={ts}{cfg['cloudinary_secret']}".encode()).hexdigest()
    r   = requests.get(
        f"https://api.cloudinary.com/v1_1/{cfg['cloudinary_cloud']}/usage",
        params={
            "api_key":   cfg["cloudinary_api_key"],
            "timestamp": ts,
            "signature": sig,
        },
        timeout=10
    )
    if r.status_code == 200:
        print("  \033[32m✓ Cloudinary credentials valid\033[0m")
    elif r.status_code == 401:
        print("  \033[31m✗ Cloudinary credentials invalid\033[0m")
    else:
        print(f"  \033[33m⚠ Cloudinary returned {r.status_code}\033[0m")
except Exception as e:
    print(f"  \033[31m✗ Cloudinary connection failed: {e}\033[0m")

# ── Vault path ──
print("  Vault path...")
vault = Path(cfg["vault_path"])
if vault.exists():
    print(f"  \033[32m✓ Vault found\033[0m")
else:
    print(f"  \033[31m✗ Vault not found: {vault}\033[0m")

print("")
PYEOF
}

# ── Install scripts ────────────────────────────────────────────────
install_scripts() {
    print_step "Installing Obsynx scripts"

    local files=("cli.py" "sync_utils.py" "obsidian_to_notion.py" "notion_to_obsidian.py" "watcher.py")

    for f in "${files[@]}"; do
        if [ ! -f "$SCRIPT_DIR/$f" ]; then
            print_err "Missing: $f — all Obsynx files must be in the same folder as install_macos.sh"
            exit 1
        fi
        cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
        print_ok "$f"
    done
}

# ── Install command ────────────────────────────────────────────────
install_command() {
    print_step "Installing 'obsynx' command"

    mkdir -p "$HOME/.local/bin"

    cat > "$BIN_PATH" << EOF
#!/usr/bin/env bash
python3 $INSTALL_DIR/cli.py "\$@"
EOF

    chmod +x "$BIN_PATH"

    RC_FILE=$(detect_rc_file)
    sed_inplace '/# obsynx PATH/,/# end obsynx PATH/d' "$RC_FILE" 2>/dev/null || touch "$RC_FILE"

    if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
        cat >> "$RC_FILE" << EOF

# obsynx PATH
export PATH="\$HOME/.local/bin:\$PATH"
# end obsynx PATH
EOF
        print_warn "Added ~/.local/bin to PATH in $RC_FILE"
    fi

    print_ok "obsynx installed to $BIN_PATH"
}

# ── Watcher: launchd / screen ──────────────────────────────────────
setup_watcher() {
    if [ "$AUTOMATE" != "y" ]; then
        print_step "Automation disabled — watcher not installed"
        print_ok "Run 'obsynx push' / 'obsynx pull' by hand whenever you want to sync"
        return
    fi

    print_step "Setting up file watcher"

    if [ "$WATCHER_MODE" = "launchd" ]; then
        mkdir -p "$HOME/Library/LaunchAgents"

        cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obsynx.watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(command -v python3)</string>
        <string>$INSTALL_DIR/watcher.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/watcher.log</string>
</dict>
</plist>
EOF

        launchctl unload "$PLIST_PATH" 2>/dev/null || true
        if launchctl load -w "$PLIST_PATH" 2>/dev/null; then
            print_ok "launchd agent installed and started"
            print_ok "Auto-starts on login"
        else
            print_warn "Could not load launchd agent — falling back to screen mode"
            WATCHER_MODE="screen"
        fi
    fi

    if [ "$WATCHER_MODE" = "screen" ]; then
        if ! command -v screen &>/dev/null; then
            print_err "screen not found — install with: brew install screen"
            return
        fi

        screen -dmS obsynx-watcher python3 "$INSTALL_DIR/watcher.py" 2>/dev/null && \
            print_ok "Watcher started in screen session: obsynx-watcher" || \
            print_warn "Could not start screen session — will auto-start on next login"

        RC_FILE=$(detect_rc_file)
        sed_inplace '/# obsynx watcher/,/# end obsynx watcher/d' "$RC_FILE" 2>/dev/null || touch "$RC_FILE"
        cat >> "$RC_FILE" << EOF

# obsynx watcher
if ! screen -list 2>/dev/null | grep -q "obsynx-watcher"; then
    screen -dmS obsynx-watcher python3 $INSTALL_DIR/watcher.py
fi
# end obsynx watcher
EOF
        print_ok "Auto-start on login added to $RC_FILE"
    fi
}

stop_watcher() {
    if launchctl list 2>/dev/null | grep -q "com.obsynx.watcher"; then
        launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
        print_ok "launchd agent stopped"
    fi
    if [ -f "$PLIST_PATH" ]; then
        rm -f "$PLIST_PATH"
        print_ok "launchd agent removed"
    fi

    if screen -list 2>/dev/null | grep -q "obsynx-watcher"; then
        screen -S obsynx-watcher -X quit 2>/dev/null || true
        print_ok "Screen session stopped"
    fi

    for RC in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
        if [ -f "$RC" ]; then
            sed_inplace '/# obsynx watcher/,/# end obsynx watcher/d' "$RC" 2>/dev/null || true
        fi
    done
}

# ── Summary ────────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║               Obsynx Installation Complete!                 ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Platform : ${CYAN}macOS${NC}"
    echo ""
    echo -e "  ${BOLD}Commands:${NC}"
    echo -e "  ${CYAN}obsynx push${NC}     — Upload vault → Notion"
    echo -e "  ${CYAN}obsynx pull${NC}     — Backup then pull Notion → Obsidian"
    echo -e "  ${CYAN}obsynx status${NC}   — Sync state, backups, logs"
    echo -e "  ${CYAN}obsynx restore${NC}  — Pick and restore a backup"
    echo -e "  ${CYAN}obsynx help${NC}     — Show all commands"
    echo ""
    echo -e "  ${BOLD}Automation:${NC}"
    if [ "$AUTOMATE" = "y" ] && [ "$WATCHER_MODE" = "launchd" ]; then
        echo -e "  Auto-push watcher: ${GREEN}ON${NC} — running as a launchd agent (auto-starts on login)"
        echo -e "  ${CYAN}launchctl list | grep obsynx${NC}"
    elif [ "$AUTOMATE" = "y" ] && [ "$WATCHER_MODE" = "screen" ]; then
        echo -e "  Auto-push watcher: ${GREEN}ON${NC} — running in screen session: obsynx-watcher"
        echo -e "  ${CYAN}screen -r obsynx-watcher${NC} to attach"
    else
        echo -e "  Auto-push watcher: ${YELLOW}OFF${NC} — run 'obsynx push' whenever you want to sync"
    fi
    echo -e "  Pulling from Notion is ${BOLD}always manual${NC} — run 'obsynx pull' yourself."
    echo -e "  Toggle automation any time: ${CYAN}./install_macos.sh${NC} → Reconfigure"
    echo ""
    echo -e "  ${BOLD}Paths:${NC}"
    echo -e "  Config  : ${CYAN}$CONFIG_FILE${NC}"
    echo -e "  Logs    : ${CYAN}$LOG_DIR/${NC}"
    echo -e "  Backups : ${CYAN}$BACKUP_PATH/${NC}"
    echo ""
    RC_FILE=$(detect_rc_file)
    echo -e "  ${YELLOW}Run: source $RC_FILE to activate the obsynx command${NC}"
    echo ""
}

# ── Uninstall ──────────────────────────────────────────────────────
run_uninstall() {
    print_step "Uninstall Obsynx"
    echo ""
    echo -e "  ${YELLOW}This will remove:${NC}"
    echo -e "  • All Obsynx scripts in $INSTALL_DIR"
    echo -e "  • The obsynx command at $BIN_PATH"
    echo -e "  • Config, logs, and state files"
    echo -e "  • Watcher launchd agent or screen session"
    echo -e "  • PATH and shell entries"
    echo ""
    echo -e "  ${YELLOW}This will NOT remove:${NC}"
    echo -e "  • Your Obsidian vault"
    echo -e "  • Your Notion pages"
    echo -e "  • Your Cloudinary images"
    echo -e "  • Your backups (stored in $INSTALL_DIR/backups)"
    echo ""
    read -rp "  Type 'yes' to confirm uninstall: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "  Cancelled."
        return
    fi

    echo ""

    stop_watcher

    # Remove obsynx command
    if [ -f "$BIN_PATH" ]; then
        rm -f "$BIN_PATH"
        print_ok "obsynx command removed"
    fi

    # Remove install dir (keep backups)
    if [ -d "$INSTALL_DIR" ]; then
        if [ -d "$INSTALL_DIR/backups" ]; then
            BACKUP_TEMP="$HOME/.obsynx-backups-temp"
            mv "$INSTALL_DIR/backups" "$BACKUP_TEMP"
        fi
        rm -rf "$INSTALL_DIR"
        if [ -d "$BACKUP_TEMP" ]; then
            mkdir -p "$HOME/.obsynx-backups"
            mv "$BACKUP_TEMP"/* "$HOME/.obsynx-backups/" 2>/dev/null || true
            rmdir "$BACKUP_TEMP" 2>/dev/null || true
            print_ok "Scripts and config removed"
            print_warn "Backups preserved at: $HOME/.obsynx-backups/"
        else
            print_ok "Scripts and config removed"
        fi
    fi

    # Clean shell config
    for RC in "$HOME/.zshrc" "$HOME/.bash_profile" "$HOME/.bashrc"; do
        if [ -f "$RC" ]; then
            sed_inplace '/# obsynx PATH/,/# end obsynx PATH/d' "$RC" 2>/dev/null || true
            sed_inplace '/# obsynx watcher/,/# end obsynx watcher/d' "$RC" 2>/dev/null || true
        fi
    done
    print_ok "Shell config cleaned"

    echo ""
    echo -e "${GREEN}${BOLD}  Obsynx uninstalled successfully.${NC}"
    echo -e "  Open a new terminal to finish cleaning your shell environment."
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────
main() {
    if [ "$(uname -s)" != "Darwin" ]; then
        print_err "This installer is for macOS only."
        echo -e "  ${YELLOW}On Linux run: ./install.sh${NC}"
        echo -e "  ${YELLOW}On Windows run: python install_windows.py${NC}"
        exit 1
    fi

    print_banner
    main_menu

    case "$MODE" in
        install)
            check_deps
            collect_config
            write_config
            install_scripts
            install_command
            setup_watcher
            print_summary
            ;;
        reconfig)
            run_reconfig
            ;;
        verify)
            run_verify
            ;;
        uninstall)
            run_uninstall
            ;;
    esac
}

main
