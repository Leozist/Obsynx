#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║                  Obsynx — Installer                         ║
# ║          Obsidian ↔ Notion Sync Tool Setup                  ║
# ╚══════════════════════════════════════════════════════════════╝

set -e

INSTALL_DIR="$HOME/.obsidian-sync"
CONFIG_FILE="$INSTALL_DIR/config.json"
LOG_DIR="$INSTALL_DIR/logs"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_PATH="$HOME/.local/bin/obsynx"

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
    echo -e "${BOLD}         Obsidian ↔ Notion Sync Tool — Installer${NC}"
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

ask_yn() {
    local prompt="$1" default="${2:-y}" result
    read -rp "  $prompt [y/n] (${default}): " result
    result="${result:-$default}"
    [[ "$result" =~ ^[Yy] ]]
}

# ── 1. Dependencies ────────────────────────────────────────────────
check_deps() {
    print_step "Checking dependencies"

    if ! command -v python3 &>/dev/null; then
        print_err "python3 not found. Install: sudo apt install python3"
        exit 1
    fi
    print_ok "python3 $(python3 --version | cut -d' ' -f2)"

    for pkg in requests watchdog; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            print_warn "$pkg not found — installing"
            pip install "$pkg" --break-system-packages -q
            print_ok "$pkg installed"
        else
            print_ok "$pkg found"
        fi
    done

    # screen for manual watcher mode
    if ! command -v screen &>/dev/null; then
        print_warn "screen not found — installing (used for background watcher)"
        sudo apt install screen -y -q
        print_ok "screen installed"
    else
        print_ok "screen found"
    fi
}

# ── 2. Collect config ──────────────────────────────────────────────
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
    echo -e "  ${BOLD}── File Watcher ────────────────────────────${NC}"
    echo -e "  ${YELLOW}The watcher monitors your vault and auto-pushes to Notion on save${NC}"
    echo ""
    echo -e "  Watcher modes:"
    echo -e "    ${CYAN}systemd${NC} — starts automatically on boot (recommended)"
    echo -e "    ${CYAN}screen${NC}  — runs in a background screen session"
    echo ""
    WATCHER_MODE=$(ask "Watcher mode [systemd/screen]" "systemd")
}

# ── 3. Write config ────────────────────────────────────────────────
write_config() {
    print_step "Writing config"

    mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$BACKUP_PATH"

    # Build JSON array from comma-separated image folders
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
    "watcher_mode": "$WATCHER_MODE",
    "install_dir": "$INSTALL_DIR"
}
EOF

    chmod 600 "$CONFIG_FILE"
    print_ok "Config saved (permissions: owner-only)"
}

# ── 4. Install scripts ─────────────────────────────────────────────
install_scripts() {
    print_step "Installing Obsynx scripts"

    local files=(
        "cli.py"
        "sync_utils.py"
        "obsidian_to_notion.py"
        "notion_to_obsidian.py"
        "watcher.py"
    )

    for f in "${files[@]}"; do
        if [ ! -f "$SCRIPT_DIR/$f" ]; then
            print_err "Missing file: $f — make sure all Obsynx files are in the same folder as install.sh"
            exit 1
        fi
        cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
        print_ok "$f"
    done
}

# ── 5. Install obsynx command ──────────────────────────────────────
install_command() {
    print_step "Installing 'obsynx' command"

    mkdir -p "$HOME/.local/bin"

    cat > "$BIN_PATH" << EOF
#!/usr/bin/env bash
python3 $INSTALL_DIR/cli.py "\$@"
EOF

    chmod +x "$BIN_PATH"

    # Ensure ~/.local/bin is in PATH
    RC_FILE=""
    if [ -f "$HOME/.zshrc" ]; then
        RC_FILE="$HOME/.zshrc"
    else
        RC_FILE="$HOME/.bashrc"
    fi

    # Remove old obsynx PATH entry if reinstalling
    sed -i '/# obsynx PATH/,/# end obsynx PATH/d' "$RC_FILE"

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

# ── 6. Setup watcher ──────────────────────────────────────────────
setup_watcher() {
    print_step "Setting up file watcher"

    if [ "$WATCHER_MODE" = "systemd" ]; then
        SERVICE_FILE="$HOME/.config/systemd/user/obsynx-watcher.service"
        mkdir -p "$(dirname "$SERVICE_FILE")"

        cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Obsynx — Obsidian Vault File Watcher
After=network.target graphical-session.target

[Service]
Type=simple
ExecStart=python3 $INSTALL_DIR/watcher.py
Restart=on-failure
RestartSec=10
StandardOutput=append:$LOG_DIR/watcher.log
StandardError=append:$LOG_DIR/watcher.log

[Install]
WantedBy=default.target
EOF

        systemctl --user daemon-reload
        systemctl --user enable obsynx-watcher.service
        systemctl --user start  obsynx-watcher.service
        print_ok "Systemd service installed and started"
        print_ok "Auto-starts on boot"

    else
        # Screen mode — start now in background
        screen -dmS obsynx-watcher python3 "$INSTALL_DIR/watcher.py"
        print_ok "Watcher started in screen session: obsynx-watcher"
        print_warn "Screen mode does NOT auto-start on boot"
        print_warn "Add this to your ~/.zshrc to auto-start on login:"
        echo -e "  ${CYAN}screen -dmS obsynx-watcher python3 $INSTALL_DIR/watcher.py${NC}"
    fi
}

# ── 7. Summary ─────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║               Obsynx Installation Complete!                 ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Commands:${NC}"
    echo -e "  ${CYAN}obsynx push${NC}     — Upload vault → Notion"
    echo -e "  ${CYAN}obsynx pull${NC}     — Backup then pull Notion → Obsidian"
    echo -e "  ${CYAN}obsynx status${NC}   — Sync state, backups, logs"
    echo -e "  ${CYAN}obsynx restore${NC}  — Pick and restore a backup"
    echo -e "  ${CYAN}obsynx help${NC}     — Show all commands"
    echo ""
    echo -e "  ${BOLD}Watcher:${NC}"
    if [ "$WATCHER_MODE" = "systemd" ]; then
        echo -e "  Running as systemd service (auto-starts on boot)"
        echo -e "  ${CYAN}systemctl --user status obsynx-watcher${NC}"
    else
        echo -e "  Running in screen session: obsynx-watcher"
        echo -e "  ${CYAN}screen -r obsynx-watcher${NC} to attach"
    fi
    echo ""
    echo -e "  ${BOLD}Paths:${NC}"
    echo -e "  Config  : ${CYAN}$CONFIG_FILE${NC}"
    echo -e "  Logs    : ${CYAN}$LOG_DIR/${NC}"
    echo -e "  Backups : ${CYAN}$BACKUP_PATH/${NC}"
    echo ""
    echo -e "  ${YELLOW}⚠  Open a new terminal or run:${NC}"
    echo -e "  ${CYAN}source ~/.zshrc${NC}"
    echo -e "  ${YELLOW}to activate the obsynx command${NC}"
    echo ""
}

# ── Main ───────────────────────────────────────────────────────────
main() {
    print_banner
    check_deps
    collect_config
    write_config
    install_scripts
    install_command
    setup_watcher
    print_summary
}

main
