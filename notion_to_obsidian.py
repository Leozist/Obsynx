#!/usr/bin/env python3
"""
Notion → Obsidian Pull Script
Pulls all pages from your Notion workspace and writes them as markdown
files into your Obsidian vault, mirroring the folder structure exactly.
Images are downloaded locally and saved to your vault screenshot folder.
Latest timestamp wins on conflicts.
"""

import os
import re
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

import sys as _sys
_sys.path.insert(0, str(Path.home() / ".obsidian-sync"))
from sync_utils import load_config as _load_config, create_backup, setup_logger

# ── CONFIG (from ~/.obsidian-sync/config.json) ──────────────────────────────────
_cfg            = _load_config()
NOTION_API_KEY  = _cfg["notion_api_key"]
ROOT_PAGE_ID    = _cfg["notion_root_page_id"]
VAULT_PATH      = _cfg["vault_path"]
IMAGE_SAVE_PATH = _cfg["image_folder_paths"][-1] if _cfg["image_folder_paths"] else VAULT_PATH / "Screenshot"
PULL_STATE_FILE = Path.home() / ".obsidian-sync" / "pull_state.json"

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── STATE ──────────────────────────────────────────────────────────────────────
def load_state():
    if PULL_STATE_FILE.exists():
        with open(PULL_STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(PULL_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── NOTION API ─────────────────────────────────────────────────────────────────
def get_block_children(block_id):
    """Fetch all children of a block, handling pagination."""
    children = []
    cursor   = None
    while True:
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{block_id}/children",
            headers=HEADERS,
            params=params
        )
        r.raise_for_status()
        data = r.json()
        children.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        time.sleep(0.3)
    return children

def get_page_metadata(page_id):
    """Get page title and last edited time."""
    r = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS)
    r.raise_for_status()
    data        = r.json()
    last_edited = data.get("last_edited_time", "")
    # Extract title
    props = data.get("properties", {})
    title = ""
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            title = "".join(p.get("plain_text", "") for p in parts)
            break
    return title, last_edited

# ── IMAGE DOWNLOADER ───────────────────────────────────────────────────────────
def download_image(url, filename):
    """Download an image from a Notion S3 URL and save it locally."""
    IMAGE_SAVE_PATH.mkdir(parents=True, exist_ok=True)
    save_path = IMAGE_SAVE_PATH / filename
    if save_path.exists():
        return filename  # Already downloaded
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(r.content)
            print(f"      🖼  Downloaded: {filename}")
            return filename
        else:
            print(f"      ⚠  Image download failed ({r.status_code}): {filename}")
            return None
    except Exception as e:
        print(f"      ⚠  Image download error: {e}")
        return None

def make_image_filename(url, block_id):
    """
    Generate a unique stable filename for a Notion image.
    Uses block_id hash to guarantee uniqueness across all images.
    Format matches Obsidian pasted image style: Pasted image YYYYMMDDHHMMSS_XXXX.png
    """
    import hashlib
    from datetime import datetime

    # Try to get extension from URL
    url_path = url.split("?")[0]
    original = url_path.split("/")[-1]
    
    # Detect extension
    ext = "png"
    for candidate in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        if original.lower().endswith(candidate):
            ext = candidate.lstrip(".")
            break

    # Use block_id hash for uniqueness — same block always = same filename
    short_hash = hashlib.md5(block_id.encode()).hexdigest()[:8].upper()
    timestamp  = datetime.now().strftime("%Y%m%d%H%M%S")
    
    return f"Pasted image {timestamp}_{short_hash}.{ext}"

# ── RICH TEXT → MARKDOWN ───────────────────────────────────────────────────────
def rich_text_to_md(rich_text):
    """Convert Notion rich_text array to markdown string."""
    result = ""
    for chunk in rich_text:
        text = chunk.get("plain_text", "")
        ann  = chunk.get("annotations", {})
        href = chunk.get("href")

        if href:
            text = f"[{text}]({href})"
        elif ann.get("code"):
            text = f"`{text}`"
        elif ann.get("bold") and ann.get("italic"):
            text = f"***{text}***"
        elif ann.get("bold"):
            text = f"**{text}**"
        elif ann.get("italic"):
            text = f"*{text}*"
        elif ann.get("strikethrough"):
            text = f"~~{text}~~"

        result += text
    return result

# ── NOTION BLOCKS → MARKDOWN ───────────────────────────────────────────────────
def blocks_to_markdown(blocks, depth=0):
    """Recursively convert Notion blocks to markdown."""
    lines  = []
    indent = "  " * depth

    for block in blocks:
        btype = block.get("type")
        data  = block.get(btype, {})
        bid   = block.get("id", "")

        # ── Headings ──
        if btype == "heading_1":
            lines.append(f"# {rich_text_to_md(data.get('rich_text', []))}")
        elif btype == "heading_2":
            lines.append(f"## {rich_text_to_md(data.get('rich_text', []))}")
        elif btype == "heading_3":
            lines.append(f"### {rich_text_to_md(data.get('rich_text', []))}")

        # ── Paragraph ──
        elif btype == "paragraph":
            text = rich_text_to_md(data.get("rich_text", []))
            lines.append(text if text else "")

        # ── Code block ──
        elif btype == "code":
            lang    = data.get("language", "plain text")
            content = rich_text_to_md(data.get("rich_text", []))
            lines.append(f"```{lang}")
            lines.append(content)
            lines.append("```")

        # ── Bullet list ──
        elif btype == "bulleted_list_item":
            text = rich_text_to_md(data.get("rich_text", []))
            lines.append(f"{indent}- {text}")

        # ── Numbered list ──
        elif btype == "numbered_list_item":
            text = rich_text_to_md(data.get("rich_text", []))
            lines.append(f"{indent}1. {text}")

        # ── To-do ──
        elif btype == "to_do":
            text    = rich_text_to_md(data.get("rich_text", []))
            checked = "x" if data.get("checked") else " "
            lines.append(f"{indent}- [{checked}] {text}")

        # ── Quote ──
        elif btype == "quote":
            text = rich_text_to_md(data.get("rich_text", []))
            lines.append(f"> {text}")

        # ── Callout (handles our tag callouts too) ──
        elif btype == "callout":
            text  = rich_text_to_md(data.get("rich_text", []))
            emoji = data.get("icon", {}).get("emoji", "💡")
            # If it was a tag callout (🏷️) restore as plain tag
            if emoji == "🏷️":
                lines.append(text)
            else:
                lines.append(f"> {emoji} {text}")

        # ── Divider ──
        elif btype == "divider":
            lines.append("---")

        # ── Image ──
        elif btype == "image":
            img_type = data.get("type")
            if img_type == "external":
                url = data.get("external", {}).get("url", "")
            else:
                url = data.get("file", {}).get("url", "")

            if url:
                filename = make_image_filename(url, bid)
                downloaded = download_image(url, filename)
                if downloaded:
                    lines.append(f"![[{downloaded}]]")
                else:
                    lines.append(f"![image]({url})")

        # ── Toggle ──
        elif btype == "toggle":
            text = rich_text_to_md(data.get("rich_text", []))
            lines.append(f"**{text}**")

        # ── Table ──
        elif btype == "table":
            # Tables handled via children
            pass

        elif btype == "table_row":
            cells = data.get("cells", [])
            row   = " | ".join(rich_text_to_md(cell) for cell in cells)
            lines.append(f"| {row} |")

        # ── Child page (sub-page reference) ──
        elif btype == "child_page":
            title = data.get("title", "Untitled")
            lines.append(f"[[{title}]]")

        # ── Blank / unsupported ──
        else:
            pass

        # ── Recurse into children ──
        if block.get("has_children") and btype not in ("child_page", "table"):
            try:
                child_blocks = get_block_children(bid)
                child_md     = blocks_to_markdown(child_blocks, depth + 1)
                if child_md:
                    lines.append(child_md)
                time.sleep(0.2)
            except Exception as e:
                print(f"      ⚠  Could not fetch children of block {bid}: {e}")

    return "\n".join(lines)

# ── VAULT PATH BUILDER ─────────────────────────────────────────────────────────
def sanitize_filename(name):
    """Make a string safe for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', '-', name)
    name = name.strip('. ')
    return name or "Untitled"

def notion_page_to_file(page_id, folder_path, state, depth=0):
    """
    Recursively process a Notion page:
    - Fetch its content and write as .md
    - Recurse into child pages
    """
    indent = "  " * depth

    try:
        title, last_edited = get_page_metadata(page_id)
        title = sanitize_filename(title) if title else "Untitled"

        # Check children first to determine if this is a folder-like page
        children = get_block_children(page_id)
        time.sleep(0.3)

        # Separate child_page blocks from content blocks
        child_pages  = [b for b in children if b.get("type") == "child_page"]
        content_blocks = [b for b in children if b.get("type") != "child_page"]

        # If this page has child pages, treat it as a folder
        if child_pages:
            sub_folder = folder_path / title
            sub_folder.mkdir(parents=True, exist_ok=True)
            print(f"{indent}📁 {title}/")

            # If there's also content, write it as a note inside the folder
            if content_blocks:
                md_content = blocks_to_markdown(content_blocks)
                write_note(sub_folder / f"{title}.md", md_content, last_edited, page_id, state, indent)

            # Recurse into child pages
            for child in child_pages:
                child_id    = child.get("id")
                child_title = child.get("child_page", {}).get("title", "Untitled")
                print(f"{indent}  📄 {child_title}")
                notion_page_to_file(child_id, sub_folder, state, depth + 1)
                time.sleep(0.3)

        else:
            # Leaf page — just write the note
            md_content = blocks_to_markdown(content_blocks)
            write_note(folder_path / f"{title}.md", md_content, last_edited, page_id, state, indent)

    except requests.exceptions.HTTPError as e:
        print(f"{indent}  ✗ {e.response.status_code}: {e.response.text[:150]}")
    except Exception as e:
        print(f"{indent}  ✗ Error: {e}")

def write_note(file_path, md_content, last_edited_notion, page_id, state, indent):
    """
    Write markdown to file using a two-factor conflict resolution:
    1. Compare sizes  — larger file wins (more content = more work done)
    2. Compare timestamps — if sizes are close (within 10%), newer wins
    Notion wins if it has meaningfully more content OR is newer with similar size.
    """
    notion_dt   = datetime.fromisoformat(last_edited_notion.replace("Z", "+00:00"))
    notion_size = len(md_content.encode("utf-8"))

    if file_path.exists():
        local_size  = file_path.stat().st_size
        local_mtime = file_path.stat().st_mtime
        local_dt    = datetime.fromtimestamp(local_mtime, tz=timezone.utc)

        # Calculate size difference as a percentage of the larger file
        max_size    = max(local_size, notion_size, 1)
        size_diff_pct = abs(local_size - notion_size) / max_size

        if size_diff_pct > 0.10:
            # Files differ by more than 10% — larger one wins (more content)
            if local_size > notion_size:
                print(f"{indent}  ⏭  {file_path.name} (local is larger, skipping)")
                return
            else:
                reason = "notion is larger"
        else:
            # Files are similar size — fall back to timestamp
            if local_dt >= notion_dt:
                print(f"{indent}  ⏭  {file_path.name} (local is newer, skipping)")
                return
            else:
                reason = "notion is newer"
    else:
        reason = "new file"

    # Write the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # Update state
    state[page_id] = last_edited_notion
    save_state(state)
    print(f"{indent}  ✅ {file_path.name} ({reason})")

# ── ENTRY POINT ────────────────────────────────────────────────────────────────
def pull():
    logger = setup_logger()
    cfg    = _load_config()

    # Always backup before pulling
    create_backup(cfg, logger)

    state = load_state()

    print(f"\n⬇️  Pulling from Notion")
    print(f"   Root page : {ROOT_PAGE_ID}")
    print(f"   Vault     : {VAULT_PATH}")
    print(f"   Images    → {IMAGE_SAVE_PATH}\n")

    # Get top-level children of the root page
    try:
        top_level = get_block_children(ROOT_PAGE_ID)
    except Exception as e:
        print(f"❌  Could not reach root page: {e}")
        return

    child_pages = [b for b in top_level if b.get("type") == "child_page"]

    if not child_pages:
        print("⚠️  No child pages found under root page.")
        print("    Make sure your integration is connected to the page.")
        return

    for block in child_pages:
        page_id = block.get("id")
        notion_page_to_file(page_id, VAULT_PATH, state, depth=0)
        time.sleep(0.3)

    print(f"\n✅ Pull complete")
    print(f"   State saved to {PULL_STATE_FILE}")

if __name__ == "__main__":
    pull()
