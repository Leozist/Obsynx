#!/usr/bin/env python3
"""
Obsidian → Notion Bulk Uploader
Uploads all markdown notes from your Obsidian vault to Notion,
preserving folder structure as nested pages.
Images uploaded to Cloudinary (private).
"""

import os
import re
import json
import time
import base64
import hashlib
import requests
from pathlib import Path

import sys as _sys
_sys.path.insert(0, str(Path.home() / ".obsidian-sync"))
from sync_utils import load_config as _load_config

# ── CONFIG (from ~/.obsidian-sync/config.json) ──────────────────────────────────
_cfg               = _load_config()
NOTION_API_KEY     = _cfg["notion_api_key"]
ROOT_PAGE_ID       = _cfg["notion_root_page_id"]
VAULT_PATH         = _cfg["vault_path"]
IMAGE_FOLDERS      = _cfg["image_folder_paths"]
CLOUDINARY_CLOUD   = _cfg["cloudinary_cloud"]
CLOUDINARY_API_KEY = _cfg["cloudinary_api_key"]
CLOUDINARY_SECRET  = _cfg["cloudinary_secret"]
STATE_FILE         = Path.home() / ".obsidian-sync" / "push_state.json"
IMG_CACHE_FILE     = Path.home() / ".obsidian-sync" / "img_cache.json"

SKIP_DIRS  = {".obsidian", ".trash", ".git"}
SKIP_FILES = {".DS_Store"}

HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ── STATE & CACHE ──────────────────────────────────────────────────────────────
def load_json(path):
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# ── CLOUDINARY UPLOAD ──────────────────────────────────────────────────────────
def upload_to_cloudinary(image_path, img_cache):
    """Upload image to Cloudinary as private. Returns URL. Caches to avoid re-uploads."""
    key = image_path.name

    if key in img_cache:
        return img_cache[key]

    try:
        timestamp = str(int(time.time()))
        sig_str   = f"timestamp={timestamp}&type=private{CLOUDINARY_SECRET}"
        signature = hashlib.sha1(sig_str.encode()).hexdigest()

        with open(image_path, "rb") as f:
            response = requests.post(
                f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/image/upload",
                data={
                    "api_key":   CLOUDINARY_API_KEY,
                    "timestamp": timestamp,
                    "signature": signature,
                    "type":      "private",
                },
                files={"file": f},
                timeout=30
            )

        if response.status_code == 200:
            url = response.json().get("secure_url", "")
            img_cache[key] = url
            save_json(IMG_CACHE_FILE, img_cache)
            return url
        else:
            print(f"      ⚠ Cloudinary {response.status_code}: {response.text[:150]}")
            return None

    except Exception as e:
        print(f"      ⚠ Upload failed ({image_path.name}): {e}")
        return None

def find_image(filename):
    """Search all screenshot folders for the image by filename."""
    for folder in IMAGE_FOLDERS:
        if not folder.exists():
            continue
        path = folder / filename
        if path.exists():
            return path
        # Glob fallback for filenames with spaces
        for ext in ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"]:
            for f in folder.glob(ext):
                if f.name == filename:
                    return f
    return None

# ── NOTION API ─────────────────────────────────────────────────────────────────
def find_existing_page(parent_id, title):
    """Search for an existing child page with the given title under parent_id."""
    try:
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{parent_id}/children",
            headers=HEADERS,
            params={"page_size": 100}
        )
        r.raise_for_status()
        for block in r.json().get("results", []):
            if block.get("type") == "child_page":
                if block.get("child_page", {}).get("title", "").strip() == title.strip():
                    return block["id"]
    except Exception:
        pass
    return None

def clear_page_blocks(page_id):
    """Delete all existing blocks from a page so it can be rewritten."""
    try:
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=HEADERS,
            params={"page_size": 100}
        )
        r.raise_for_status()
        for block in r.json().get("results", []):
            requests.delete(
                f"https://api.notion.com/v1/blocks/{block['id']}",
                headers=HEADERS
            )
            time.sleep(0.1)
    except Exception as e:
        print(f"    ⚠ Could not clear page blocks: {e}")

def create_notion_page(parent_id, title, blocks=None):
    """Create a new page or update existing one with the same title."""
    existing_id = find_existing_page(parent_id, title)

    if existing_id:
        # Page exists — clear it and rewrite
        clear_page_blocks(existing_id)
        if blocks:
            append_blocks(existing_id, blocks[:100])
            if len(blocks) > 100:
                append_blocks(existing_id, blocks[100:])
        return existing_id

    # Page does not exist — create fresh
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": {
                "title": [{"type": "text", "text": {"content": title[:2000]}}]
            }
        },
    }
    if blocks:
        payload["children"] = blocks[:100]

    r = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=payload)
    r.raise_for_status()
    page_id = r.json()["id"]

    if blocks and len(blocks) > 100:
        append_blocks(page_id, blocks[100:])

    return page_id

def append_blocks(page_id, blocks):
    for i in range(0, len(blocks), 100):
        batch = blocks[i:i+100]
        r = requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=HEADERS,
            json={"children": batch}
        )
        if r.status_code != 200:
            print(f"    ⚠ Append error: {r.status_code} {r.text[:150]}")
        time.sleep(0.35)

# ── INLINE MARKDOWN PARSER ─────────────────────────────────────────────────────
def parse_inline(text):
    if not text:
        return [{"type": "text", "text": {"content": ""}}]

    rich    = []
    pattern = re.compile(
        r'(`[^`]+`)'
        r'|(\*\*[^*]+\*\*)'
        r'|(\*[^*]+\*|_[^_]+_)'
        r'|(\[([^\]]+)\]\(([^)]+)\))'
        r'|(\[\[([^\]]+)\]\])'
    )
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            rich.append({"type": "text", "text": {"content": text[last:m.start()]}})
        s = m.group(0)
        if s.startswith('`'):
            rich.append({"type": "text", "text": {"content": s[1:-1]}, "annotations": {"code": True}})
        elif s.startswith('**'):
            rich.append({"type": "text", "text": {"content": s[2:-2]}, "annotations": {"bold": True}})
        elif s.startswith('*') or s.startswith('_'):
            rich.append({"type": "text", "text": {"content": s[1:-1]}, "annotations": {"italic": True}})
        elif s.startswith('[') and '](' in s:
            rich.append({"type": "text", "text": {"content": m.group(5), "link": {"url": m.group(6)}}})
        elif s.startswith('[['):
            rich.append({"type": "text", "text": {"content": m.group(8)}})
        last = m.end()

    if last < len(text):
        rich.append({"type": "text", "text": {"content": text[last:]}})

    return rich if rich else [{"type": "text", "text": {"content": text}}]

def map_language(lang):
    mapping = {
        "ps1": "powershell", "powershell": "powershell",
        "bash": "bash", "sh": "bash", "shell": "bash",
        "python": "python", "py": "python",
        "js": "javascript", "javascript": "javascript",
        "ts": "typescript", "sql": "sql", "json": "json",
        "yaml": "yaml", "html": "html", "css": "css",
        "go": "go", "rust": "rust", "c": "c", "cpp": "c++",
        "java": "java", "xml": "xml", "markdown": "markdown", "md": "markdown",
    }
    return mapping.get(lang.lower().strip(), "plain text")

def make_code_blocks(code_content, lang):
    """Split code content into chunks of 1900 chars to stay under Notion's 2000 char limit."""
    LIMIT = 1900
    language = map_language(lang)
    if len(code_content) <= LIMIT:
        return [{
            "object": "block",
            "type":   "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": code_content}}],
                "language":  language
            }
        }]
    # Split on newlines to avoid cutting mid-line
    chunks = []
    current = []
    current_len = 0
    for line in code_content.split("\n"):
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > LIMIT and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = line_len
        else:
            current.append(line)
            current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return [{
        "object": "block",
        "type":   "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": chunk}}],
            "language":  language
        }
    } for chunk in chunks]

# ── MARKDOWN → NOTION BLOCKS ───────────────────────────────────────────────────
def md_to_notion_blocks(content, img_cache):
    blocks          = []
    lines           = content.split("\n")
    i               = 0
    in_code_block   = False
    code_lang       = ""
    code_lines      = []
    in_frontmatter  = False

    while i < len(lines):
        line = lines[i]

        # Frontmatter
        if i == 0 and line.strip() == "---":
            in_frontmatter = True
            i += 1
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            i += 1
            continue

        # Code blocks
        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang     = line[3:].strip() or "plain text"
                code_lines    = []
            else:
                in_code_block = False
                blocks.extend(make_code_blocks("\n".join(code_lines), code_lang))
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # Headings h1–h6 (h4-h6 remapped to h3)
        h = re.match(r'^(#{1,6})\s+(.*)', line)
        if h:
            level = min(len(h.group(1)), 3)
            htype = f"heading_{level}"
            blocks.append({
                "object": "block",
                "type":   htype,
                htype:    {"rich_text": parse_inline(h.group(2))}
            })
            i += 1
            continue

        # Obsidian image ![[filename.png]]
        obs_img = re.match(r'!\[\[([^\]]+\.(png|jpg|jpeg|gif|webp))\]\]', line.strip(), re.IGNORECASE)
        if obs_img:
            blocks.append(make_image_block(obs_img.group(1), img_cache))
            i += 1
            continue

        # Standard markdown image ![alt](src)
        std_img = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if std_img:
            src = std_img.group(2)
            if src.startswith("http"):
                blocks.append({
                    "object": "block",
                    "type":   "image",
                    "image":  {"type": "external", "external": {"url": src}}
                })
            else:
                blocks.append(make_image_block(Path(src).name, img_cache))
            i += 1
            continue

        # Obsidian tag on its own line #TagName
        tag = re.match(r'^#([A-Za-z][A-Za-z0-9_-]*)$', line.strip())
        if tag:
            blocks.append({
                "object": "block",
                "type":   "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": line.strip()}}],
                    "icon":      {"type": "emoji", "emoji": "🏷️"},
                    "color":     "purple_background"
                }
            })
            i += 1
            continue

        # Divider
        if re.match(r'^---+$|^\*\*\*+$', line.strip()):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # Checkbox
        chk = re.match(r'^\s*-\s+\[([ xX])\]\s+(.*)', line)
        if chk:
            blocks.append({
                "object": "block",
                "type":   "to_do",
                "to_do": {
                    "rich_text": parse_inline(chk.group(2)),
                    "checked":   chk.group(1).lower() == "x"
                }
            })
            i += 1
            continue

        # Bullet list
        bul = re.match(r'^\s*[-*+]\s+(.*)', line)
        if bul:
            blocks.append({
                "object": "block",
                "type":   "bulleted_list_item",
                "bulleted_list_item": {"rich_text": parse_inline(bul.group(1))}
            })
            i += 1
            continue

        # Numbered list
        num = re.match(r'^\s*\d+\.\s+(.*)', line)
        if num:
            blocks.append({
                "object": "block",
                "type":   "numbered_list_item",
                "numbered_list_item": {"rich_text": parse_inline(num.group(1))}
            })
            i += 1
            continue

        # Blockquote
        if line.startswith(">"):
            blocks.append({
                "object": "block",
                "type":   "quote",
                "quote":  {"rich_text": parse_inline(line[1:].strip())}
            })
            i += 1
            continue

        # Empty line
        if not line.strip():
            i += 1
            continue

        # Paragraph
        blocks.append({
            "object": "block",
            "type":   "paragraph",
            "paragraph": {"rich_text": parse_inline(line)}
        })
        i += 1

    # Close unclosed code block
    if in_code_block and code_lines:
        blocks.extend(make_code_blocks("\n".join(code_lines), code_lang))

    return blocks

def make_image_block(filename, img_cache):
    local = find_image(filename)
    if local:
        url = upload_to_cloudinary(local, img_cache)
        if url:
            print(f"      🖼  {filename} → uploaded ✓")
            return {
                "object": "block",
                "type":   "image",
                "image":  {"type": "external", "external": {"url": url}}
            }

    print(f"      ⚠  Image not found: {filename}")
    return {
        "object": "block",
        "type":   "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"[image: {filename}]"}}],
            "icon":      {"type": "emoji", "emoji": "🖼️"},
            "color":     "gray_background"
        }
    }

# ── VAULT WALKER ───────────────────────────────────────────────────────────────
def upload_vault():
    state     = load_json(STATE_FILE)
    img_cache = load_json(IMG_CACHE_FILE)
    stats     = {"created": 0, "skipped": 0, "errors": 0}

    def walk(dir_path, parent_id, depth=0):
        indent  = "  " * depth
        entries = sorted(dir_path.iterdir())
        dirs    = [e for e in entries if e.is_dir()  and e.name not in SKIP_DIRS]
        files   = [e for e in entries if e.is_file() and e.suffix == ".md" and e.name not in SKIP_FILES]

        for file in files:
            rel   = str(file.relative_to(VAULT_PATH))
            mtime = file.stat().st_mtime

            if state.get(rel) == mtime:
                # mtime matches — but verify the page actually exists in Notion
                existing = find_existing_page(parent_id, file.stem)
                if existing:
                    print(f"{indent}  ⏭  {file.name} (unchanged)")
                    stats["skipped"] += 1
                    continue
                else:
                    # State says uploaded but page is missing — force re-push
                    print(f"{indent}  📄 {file.name} (missing from Notion — re-pushing)")
                    del state[rel]

            print(f"{indent}  📄 {file.name}")
            try:
                content = file.read_text(encoding="utf-8", errors="ignore")
                blocks  = md_to_notion_blocks(content, img_cache)
                page_id = create_notion_page(parent_id, file.stem, blocks[:100])

                if len(blocks) > 100:
                    append_blocks(page_id, blocks[100:])

                state[rel] = mtime
                save_json(STATE_FILE, state)
                stats["created"] += 1
                time.sleep(0.4)

            except requests.exceptions.HTTPError as e:
                print(f"{indent}  ✗ {e.response.status_code}: {e.response.text[:150]}")
                stats["errors"] += 1
            except Exception as e:
                print(f"{indent}  ✗ {e}")
                stats["errors"] += 1

        for d in dirs:
            print(f"{indent}📁 {d.name}/")
            try:
                folder_id = create_notion_page(parent_id, d.name)
                time.sleep(0.3)
                walk(d, folder_id, depth + 1)
            except Exception as e:
                print(f"{indent}  ✗ Folder error: {e}")
                stats["errors"] += 1

    print(f"\n🚀 Starting upload")
    print(f"   Vault  : {VAULT_PATH}")
    print(f"   Notion : {ROOT_PAGE_ID}")
    print(f"   Images : {len(IMAGE_FOLDERS)} folders\n")

    walk(VAULT_PATH, ROOT_PAGE_ID)

    print(f"\n✅ Done!")
    print(f"   Created : {stats['created']} pages")
    print(f"   Skipped : {stats['skipped']} unchanged")
    print(f"   Errors  : {stats['errors']}")

# ── ENTRY POINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    upload_vault()
