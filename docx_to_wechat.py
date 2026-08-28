#!/usr/bin/env python3
"""
docx_to_wechat.py — 基于精选日报 Word 底稿生成公众号粘贴 HTML

输入：精选日报_YYYY-MM-DD_*.docx 或 .md/.markdown（结构化底稿）
输出：
  公众号文章_{date}.html      浏览器预览版（含 <style> 外壳）
  公众号粘贴版_{date}.html    纯内联片段，粘贴进公众号编辑器
  公众号元数据_{date}.json    元数据

设计依据：Word 底稿的稳定结构规律（兼容 Word 原生列表经 Pandoc 转换后的写法）
  # 飞客日报 📋 YYYY-MM-DD
  抓取时间 HH:MM | 共 N 条讨论 | 新卡X 权益变更X 活动X 其他X | 数据源：...
  ## 一级板块（6 个：热门讨论/新卡发行&申卡下卡/权益变更/退发退市/活动优惠/其他）
  ### {银行} {一句话摘要} {标签emoji?}      埖子卡片头
  • 🔗 {标题}：{url}                          银行+标题+原帖
  • 📊 {N}回 / {N}阅                          回复数+阅读数
  • 💬 点评：{定制批注}                       编辑点评
  （本日无相关讨论）                            餽板块占位
  

视觉模板复用 0709 前两条卡片：左边色条+银行标签+分类副标+数据行+点评气泡+按钮式原帖链接。
约束：公众号粘贴只认内联 style，禁用 <style>/JS/外部资源/外部字体/class。

格式兼容：卡体列表兼容 `-`、`*`、`•` 前缀；热门榜单兼容 `1.`、`1\.`，以及 `📋 标题：https://...（N回/N阅）`；
元信息兼容 Pandoc 引用块；分类标签支持 `🔴`、`🟡`、`🐷`、`⚪`。

Skill 选型：docx（解析 .docx）+ frontend-design 设计原则（产出模板）。

用法：
  python docx_to_wechat.py 精选日报_0709_*.docx
  python docx_to_wechat.py 精选日报_0731_*.md
  python docx_to_wechat.py 精选日报_0731_*.md --paste-only
  python docx_to_wechat.py 精选日报_0709_*.docx --out-dir _site
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    from publishing_helpers import gen_editor_note
except Exception:  # 独立运行时降级
    gen_editor_note = None

# ── 银行→主色 映射（扫读时一眼区分）────────────────────────────────
BANK_COLOR = {
    "工商银行": "#dc2626", "工行": "#dc2626", "工银": "#dc2626",
    "汇丰银行": "#ea580c", "汇丰": "#ea580c", "比丰": "#ea580c",
    "中信银行": "#2563eb", "中信": "#2563eb",
    "农行": "#16a34a", "农业银行": "#16a34a", "老农": "#16a34a",
    "交通银行": "#7c3aed", "交行": "#7c3aed", "沃德": "#7c3aed",
    "邮储银行": "#d97706", "邮储": "#d97706",
    "招商银行": "#db2777", "招行": "#db2777", "招行": "#db2777",
    "浦发银行": "#0d9488", "浦发": "#0d9488", "浦发": "#0d9488",
    "中国银行": "#475569", "中行": "#475569",
    "平安银行": "#059669", "平安": "#059669",
    "光大银行": "#9333ea", "光大": "#9333ea",
}
DEFAULT_BANK_COLOR = "#78716c"

# 标签 emoji → 分类副标签文案
TAG_LABEL = {
    "🔴": "高价值", "🟡": "中等", "🐷": "套路",
    "⚪": "套路",
}

# 板块图标
SECTION_ICON = {
    "热门讨论": "🔥", "新卡发行&申卡下卡": "🆕", "新卡发行": "🆕", "权益变更": "⚠️",
    "退发退市": "📉", "活动优惠": "🎁", "公告通知": "📢", "疑问求助": "❓",
    "用卡经验": "💳", "其他": "📌",
}

ARTICLE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Helvetica Neue",sans-serif;background:#f5f5f5;color:#1a1a1a;padding:0;max-width:640px;margin:0 auto;line-height:1.8}
.article{background:#fff;padding:20px 16px 30px}
"""


def _read_markdown(md_path: Path) -> str:
    """读取 Markdown，兼容 Windows 常见 UTF-8 BOM。"""
    return md_path.read_text(encoding="utf-8-sig")


def extract_markdown(input_path: Path) -> str:
    """读取 Markdown，或将 DOCX 提取为 Markdown。

    Markdown 直接进入现有解析器，避免先转 DOCX 再反向提取造成格式损失。
    DOCX 仍沿用 Pandoc，并保留 python-docx 降级路径。
    """
    if input_path.suffix.lower() in {".md", ".markdown"}:
        return _read_markdown(input_path)
    if input_path.suffix.lower() != ".docx":
        raise ValueError("仅支持 .docx、.md 和 .markdown 输入文件")

    try:
        result = subprocess.run(
            ["pandoc", str(input_path), "-t", "markdown", "--wrap=none"],
            capture_output=True, text=True, check=True, encoding="utf-8",
        )
        return result.stdout
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, FileNotFoundError):
            print("[-] pandoc 未安装，降级到 python-docx", file=sys.stderr)
        return _extract_via_python_docx(input_path)


def _extract_via_python_docx(docx_path: Path) -> str:
    """pandoc 不可用时的降级解析：逐段拼 markdown。"""
    import docx
    d = docx.Document(str(docx_path))
    lines = []
    for p in d.paragraphs:
        txt = p.text.strip()
        if not txt:
            lines.append("")
            continue
        style = (p.style.name or "").lower()
        if style.startswith("heading 1") or style == "title":
            lines.append(f"# {txt}")
        elif style.startswith("heading 2"):
            lines.append(f"## {txt}")
        elif style.startswith("heading 3"):
            lines.append(f"### {txt}")
        else:
            lines.append(txt)
    return "\n".join(lines)


# ── 解析 markdown 成结构化日报 ─────────────────────────────────────
def parse_daily(md: str) -> dict:
    """把 markdown 解析成 {date, meta, sections:[{name, posts:[...]}]}。"""
    if _looks_like_optimized_report(md):
        return _parse_optimized_report(md)
    lines = md.splitlines()
    daily = {"date": "", "meta": "", "sections": []}

    # 日报标题行取日期
    for line in lines:
        m = re.match(r"^#\s*飞客日报\s*📋?\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            daily["date"] = m.group(1)
            break

    # 元信息行
    for line in lines:
        # Pandoc 会把 Word 中的摘要段落转换成 Markdown 引用块（> ...）。
        meta_line = line.strip()
        if meta_line.startswith(">"):
            meta_line = meta_line[1:].strip()
        meta_line = meta_line.replace(r"\|", "|")
        if (
            meta_line.startswith(("抓取时间", "|"))
            or re.match(r"^共\s*\d+\s*条讨论\b", meta_line)
        ):
            # 摘要中的“新卡”统一改成“新卡/下卡”。
            meta_line = re.sub(r"新卡(?!发行|/下卡)", "新卡/下卡", meta_line)
            daily["meta"] = meta_line
            break

    # 板块解析
    cur_section = None
    cur_post = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # 一级板块
        m1 = re.match(r"^##\s+(.+)$", line)
        if m1:
            # 落尾
            if cur_post and cur_section:
                cur_section["posts"].append(cur_post)
                cur_post = None
            if cur_section:
                daily["sections"].append(cur_section)
            name = m1.group(1).strip()
            name = name.replace("新卡发行", "新卡发行&申卡下卡")
            # 剥离板块名前的 emoji
            name_clean = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", name)
            cur_section = {"name": name_clean, "raw": name, "posts": []}
            i += 1
            continue
        # 空板块占位
        if "（本日无相关讨论）" in line or "(本日无相关讨论)" in line:
            if cur_section:
                cur_section["empty"] = True
            i += 1
            continue
        # 三级/四级帖子卡片头（兼容 `### 帖子` 与嵌套分组下的 `#### 帖子`）
        m3 = re.match(r"^#{3,4}\s+(.+)$", line)
        if m3 and cur_section is not None:
            if cur_post:
                cur_section["posts"].append(cur_post)
            head = m3.group(1).strip()
            cur_post = _parse_post_head(head)
            i += 1
            continue
        # 榜单行（热门讨论等有序列表：pandoc 转义为 `1\. **标题**（N回/N阅）[银行]`）
        # Pandoc 可能输出 `1.`，也可能输出转义后的 `1\.`。
        m_num = re.match(r"^(\d+)(?:\\)?\.\s+(.+)$", line)
        if m_num and cur_section is not None:
            if cur_post:
                cur_section["posts"].append(cur_post)
                cur_post = None
            cur_section["posts"].append(_parse_list_item(m_num.group(2).strip()))
            i += 1
            continue
        # 三行卡体
        if cur_post is not None:
            # Word 原生列表经 Pandoc 通常变成 `-`，旧底稿可能是字面量 `•`。
            if re.match(r"^(?:[-*•]\s*)?(?:🔗|📋)", line):
                _parse_post_link(line, cur_post)
            elif re.match(r"^(?:[-*•]\s*)?📊", line):
                _parse_post_stats(line, cur_post)
            elif re.match(r"^(?:[-*•]\s*)?💬", line):
                _parse_post_note(line, cur_post)
        i += 1

    # 落尾
    if cur_post and cur_section:
        cur_section["posts"].append(cur_post)
    if cur_section:
        daily["sections"].append(cur_section)

    # Enrich ranked items from later detail cards by URL.
    posts_by_url = {
        p.get("url"): p
        for s in daily["sections"]
        for p in s["posts"]
        if p.get("url")
    }
    posts_by_title = {
        re.sub(r"\s+", "", (p.get("title") or p.get("summary") or "").strip()): p
        for s in daily["sections"]
        for p in s["posts"]
        if p.get("url")
    }
    for section in daily["sections"]:
        for post in section["posts"]:
            if not post.get("is_list_item"):
                continue
            detail = posts_by_url.get(post.get("url"))
            if detail is None:
                key = re.sub(r"\s+", "", (post.get("title") or "").strip())
                detail = posts_by_title.get(key)
            if detail:
                post["bank"] = detail.get("bank", "")
                post["url"] = detail.get("url", post.get("url", ""))
                if not post.get("title"):
                    post["title"] = detail.get("title", "")
                if detail.get("summary"):
                    post["summary"] = detail.get("summary", "")
                if detail.get("note"):
                    post["note"] = detail.get("note", "")
                if detail.get("tag_label"):
                    post["tag_label"] = detail.get("tag_label", "")
                if post.get("replies") == "?":
                    post["replies"] = detail.get("replies", "?")
                if post.get("views") == "?":
                    post["views"] = detail.get("views", "?")

    # Keep one hot section and one card per forum thread.
    seen_tids = set()
    seen_hot = False
    clean_sections = []
    for section in daily["sections"]:
        if "热门讨论" in section["name"]:
            if seen_hot:
                continue
            seen_hot = True
        posts = []
        for post in section["posts"]:
            match = re.search(r"tid=(\d+)", post.get("url", ""))
            tid = match.group(1) if match else ""
            if tid and tid in seen_tids:
                continue
            if tid:
                seen_tids.add(tid)
            posts.append(post)
        section["posts"] = posts
        clean_sections.append(section)
    daily["sections"] = clean_sections

    return daily


def _looks_like_optimized_report(md: str) -> bool:
    """识别已经写成日报正文的 Markdown，避免套用旧卡片底稿解析器。"""
    return bool(re.search(r"(?m)^##\s+(?:🔥\s*)?今日焦点\s*$", md)) and bool(
        re.search(r"(?m)^###\s+", md)
    )


def _parse_optimized_report(md: str) -> dict:
    """保留优化版日报原文，供 Markdown 保真渲染分支使用。"""
    title = ""
    report_date = ""
    for line in md.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if m and not title:
            title = m.group(1).strip()
        dm = re.search(r"(\d{4}-\d{2}-\d{2})", line)
        if dm and not report_date:
            report_date = dm.group(1)
    meta = ""
    for line in md.splitlines():
        candidate = line.strip()
        if candidate.startswith(">"):
            candidate = candidate[1:].strip()
        if re.match(r"^共\s*\d+\s*条讨论\b", candidate):
            meta = candidate
            break
    return {
        "date": report_date,
        "meta": meta,
        "sections": [{"name": "优化版正文", "posts": [{"body": md}]}],
        "optimized": True,
        "markdown": md,
        "article_title": title or f"飞客日报 | {report_date}",
    }


def _parse_post_head(head: str) -> dict:
    """`{银行} {一句话摘要} {标签emoji?}` → {bank, summary, tag, tag_label}。"""
    # 末尾 emoji 标签（如 🔴高价值/🟡中等/🐷套路）
    tag = ""
    tag_label = ""
    m = re.search(r"(🔴|🟡|🐷|⚪)([\u4e00-\u9fa5]+)?\s*$", head)
    if m:
        tag = m.group(1)
        tag_label = m.group(2) or TAG_LABEL.get(tag, "")
        head = head[: m.start()].strip()

    # 银行名：首个空格前，支持两字、三字、四字银行名
    bank = ""
    # 优先匹配已知银行名
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if head.startswith(name):
            bank = name
            break
    if bank:
        summary = head[len(bank) :].strip()
    else:
        # 未识别到银行时，不把整段摘要误当成长银行标签。
        bank = "其他"
        summary = head

    return {
        "bank": bank,
        "summary": summary,
        "tag": tag,
        "tag_label": tag_label,
        "title": "",
        "url": "",
        "replies": "?",
        "views": "?",
        "note": "",
    }


def _parse_number(num_str: str, context_str: str) -> int:
    """解析数字，支持 K/M 后缀。例如 '8.4' + '8.4K' → 8400。"""
    try:
        val = float(num_str)
        if "K" in context_str or "k" in context_str:
            return int(val * 1000)
        elif "M" in context_str or "m" in context_str:
            return int(val * 1000000)
        return int(val)
    except (ValueError, TypeError):
        return 0


def _parse_post_link(line: str, post: dict) -> None:
    """`• 🔗 {标题}：{url}` 或标题内含空格再接 url。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = re.sub(r"^(?:🔗|📋)\s*", "", body)  # 去链接图标
    # 按 url 切：第一个 http 出现处
    m = re.search(r"(https?://\S+)", body)
    if m:
        post["url"] = m.group(1).rstrip("：:")
        title_part = body[: m.start()].rstrip("：:").strip()
        post["title"] = title_part
    else:
        post["title"] = body


def _parse_post_stats(line: str, post: dict) -> None:
    """`• 📊 {N}回 / {N}阅` 或 `{N}回 / {N}K阅`。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = body[1:].strip() if body.startswith("📊") else body
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:K|M)?\s*回\s*/\s*(\d+(?:\.\d+)?)\s*(?:K|M)?\s*阅", body)
    if m:
        replies_str = m.group(1)
        views_str = m.group(2)
        # 从整个匹配字符串中提取 K/M 修饰符
        full_match = m.group(0)
        # 回复数：检查回复部分是否有 K/M
        replies_part = full_match[: full_match.find("回")].strip()
        views_part = full_match[full_match.find("/")+1: full_match.find("阅")].strip()
        post["replies"] = _parse_number(replies_str, replies_part)
        post["views"] = _parse_number(views_str, views_part)


def _parse_post_note(line: str, post: dict) -> None:
    """`• 💬 点评：{定制批注}`。"""
    body = re.sub(r"^[-*•]\s*", "", line).strip()
    body = body[1:].strip() if body.startswith("💬") else body
    body = re.sub(r"^点评[：:]\s*", "", body)
    post["note"] = body.strip()


def _parse_list_item(body: str) -> dict:
    """热门讨论榜单行：`**标题**（N回/N阅）[银行]`（pandoc 转义后）。

    pandoc 输出会把 markdown 的 `*` `[` `]` 反斜杠转义为 `\\*` `\\[` `\\]`，
    本函数剥掉转义再抽字段。无 url/点评，但有标题/银行/回复/阅读数。
    """
    # 剥 pandoc 转义反斜杠
    clean = body.replace("\\*", "*").replace("\\[", "[").replace("\\]", "]").replace("\\(", "(").replace("\\)", ")")
    # Title may be bold markdown or a plain icon-prefixed title followed by URL.
    title = ""
    m = re.search(r"\*\*([^*]+)\*\*", clean)
    if m:
        title = m.group(1).strip()
        clean = clean[: m.start()] + clean[m.end() :]

    url = ""
    url_match = re.search(r"(https?://[^\s（(]+)", clean)
    if url_match:
        url = url_match.group(1).rstrip("：:")
        if not title:
            title = clean[: url_match.start()].strip()
        clean = clean[: url_match.start()] + clean[url_match.end() :]
    title = re.sub(r"^(?:📋|🔗)\s*", "", title).strip()
    title = re.sub(r"[：:]\s*$", "", title).strip()
    # 回复/阅读在 （N回/N阅） 或 （N.NK回/N.NK阅）
    replies = "?"
    views = "?"
    m = re.search(r"（(\d+(?:\.\d+)?)\s*(?:K|M)?\s*回\s*/\s*(\d+(?:\.\d+)?)\s*(?:K|M)?\s*阅）", clean)
    if m:
        full_match = m.group(0)
        # 提取 K/M 修饰符
        replies_part = full_match[1: full_match.find("回")].strip()  # 去掉 （和找到 回 之前的部分
        views_part = full_match[full_match.find("/")+1: full_match.find("阅")].strip()
        replies = _parse_number(m.group(1), replies_part)
        views = _parse_number(m.group(2), views_part)
        clean = clean[: m.start()] + clean[m.end() :]
    # 银行在 [xxx]
    bank = ""
    m = re.search(r"\[([^\]]+)\]", clean)
    if m:
        bank = m.group(1).strip()
        clean = clean[: m.start()] + clean[m.end() :]
    if not title:
        title = re.sub(r"^(?:📋|🔗)\s*", "", clean).strip()
        title = re.sub(r"[：:]\s*$", "", title).strip()
    # 银行名归一（榜单用简称，归一到色映射键）
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if bank.startswith(name) or name.startswith(bank):
            bank = name
            break
    return {
        "bank": bank,
        "summary": "",
        "tag": "",
        "tag_label": "",
        "title": title,
        "url": url,
        "replies": replies,
        "views": views,
        "note": "",
        "is_list_item": True,
    }


def _clean_category_stats(meta: str) -> str:
    """移除分类统计中的 0 条项，使概览行更简洁。

    输入：> 共 17 条讨论 | 新卡发行 0 条 | 权益变更 1 条 | ... | 其他 0 条 | 数据源：...
    输出：> 共 17 条讨论 | 权益变更 1 条 | ... | 数据源：...
    """
    if not meta or "0 条" not in meta:
        return meta
    parts = meta.split(" | ")
    cleaned = []
    for part in parts:
        if " 0 条" in part:
            continue
        cleaned.append(part)
    return " | ".join(cleaned)


# ── HTML 生成 ─────────────────────────────────────────────────────
def _bank_color(bank: str) -> str:
    return BANK_COLOR.get(bank, DEFAULT_BANK_COLOR)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc_attr(s: str) -> str:
    return html.escape(s or "", quote=True)


def _inline_markdown(text: str) -> str:
    """渲染优化版正文中常用的粗体、链接和行内代码。"""
    tokens = []

    def save_link(match: re.Match) -> str:
        label = _inline_markdown(match.group(1))
        url = _esc_attr(match.group(2))
        tokens.append(f'<a href="{url}" style="color:#4f46e5;text-decoration:none">{label}</a>')
        return f"\x00{len(tokens) - 1}\x00"

    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", save_link, text)
    value = _esc(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"`([^`]+)`", r"<code style=\"background:#f1f5f9;padding:1px 4px;border-radius:3px\">\1</code>", value)
    for idx, token in enumerate(tokens):
        value = value.replace(f"\x00{idx}\x00", token)
    return value


def _render_optimized_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and not all(re.fullmatch(r"[-: ]+", cell or "-") for cell in cells):
            rows.append(cells)
    if not rows:
        return ""
    head = "".join(f'<th style="border:1px solid #e5e7eb;padding:7px 8px;background:#f8fafc;text-align:left">{_inline_markdown(c)}</th>' for c in rows[0])
    body = "".join(
        '<tr>' + "".join(f'<td style="border:1px solid #e5e7eb;padding:7px 8px;vertical-align:top">{_inline_markdown(c)}</td>' for c in row) + '</tr>'
        for row in rows[1:]
    )
    return f'<div style="overflow-x:auto;margin:10px 0"><table style="border-collapse:collapse;width:100%;font-size:12px;line-height:1.6"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _render_optimized_blocks(lines: list[str], thread_stats: dict | None = None) -> str:
    parts = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---":
            i += 1
            continue
        if line.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            text = " ".join(quote).strip()
            if text:
                tid_match = re.search(r"tid=(\d+)", text)
                stat = (thread_stats or {}).get(tid_match.group(1), {}) if tid_match else {}
                if stat and re.search(r"｜\?回/\?阅", text):
                    text = re.sub(r"｜\?回/\?阅", f"｜{stat.get('replies', '?')}回/{stat.get('views', '?')}阅", text)
                link_match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", text)
                if link_match:
                    url = link_match.group(2)
                    rest = text[link_match.end():]
                    text = f"🔗 原帖 [{url}]({url}){rest}"
                parts.append(f'<div style="font-size:13px;color:#64748b;margin:8px 0;padding:9px 12px;background:#f8fafc;border-left:3px solid #cbd5e1">{_inline_markdown(text)}</div>')
            continue
        if re.match(r"^\|", line):
            table = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            parts.append(_render_optimized_table(table))
            continue
        list_match = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", line)
        if list_match:
            items = []
            ordered = bool(re.match(r"^\d+\.", line))
            while i < len(lines):
                m = re.match(r"^(?:[-*]|\d+\.)\s+(.+)$", lines[i].strip())
                if not m or bool(re.match(r"^\d+\.", lines[i].strip())) != ordered:
                    break
                items.append(f'<li style="margin:3px 0">{_inline_markdown(m.group(1))}</li>')
                i += 1
            tag = "ol" if ordered else "ul"
            parts.append(f'<{tag} style="margin:6px 0 10px 20px;padding:0;font-size:14px;line-height:1.7">{"".join(items)}</{tag}>')
            continue
        parts.append(f'<p style="font-size:14px;color:#334155;margin:7px 0;line-height:1.75">{_inline_markdown(line)}</p>')
        i += 1
    return "".join(parts)


def build_optimized_body(daily: dict) -> str:
    """把优化版日报按原有层级渲染为可粘贴的内联 HTML。"""
    lines = daily["markdown"].splitlines()
    # 去掉 AIGC front matter，避免把机器元信息展示给读者。
    if lines and lines[0].strip() == "---":
        try:
            end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
            lines = lines[end + 1 :]
        except StopIteration:
            pass
    parts = []
    meta = _clean_category_stats(daily.get("meta", ""))
    return "".join(_render_optimized_in_source_order(lines, meta, daily.get("thread_stats", {})))


def _render_optimized_in_source_order(lines: list[str], meta: str, thread_stats: dict | None = None) -> list[str]:
    result = []
    if meta:
        result.append(f'<p style="font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;background:#f8f9fa;border-radius:8px;line-height:1.6">📊 <strong>今日概览</strong> — {_inline_markdown(meta)}</p>')
    current_section = None
    current_title = None
    body = []

    def flush():
        nonlocal current_title, body
        if current_title:
            result.append(f'<div style="margin:10px 0;padding:13px 14px;background:#f8fafc;border:1px solid #e5e7eb;border-left:4px solid #6366f1;border-radius:6px"><div style="font-size:16px;font-weight:700;color:#0f172a;line-height:1.5">{_inline_markdown(current_title)}</div>{_render_optimized_blocks(body, thread_stats)}</div>')
        elif body:
            result.append(_render_optimized_blocks(body, thread_stats))
        current_title = None
        body = []

    for raw in lines:
        line = raw.strip()
        if not line or line == "---" or line.startswith("# "):
            continue
        m2 = re.match(r"^##\s+(.+)$", line)
        if m2:
            flush()
            current_section = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", m2.group(1)).strip()
            icon = SECTION_ICON.get(current_section, "")
            result.append(f'<p style="font-size:16px;font-weight:700;color:#1e293b;margin:20px 0 9px;padding-left:10px;border-left:3px solid #6366f1">{icon} {_inline_markdown(current_section)}</p>')
            continue
        m3 = re.match(r"^###\s+(.+)$", line)
        if m3:
            flush()
            current_title = m3.group(1).strip()
            continue
        if current_section is not None:
            body.append(raw)
    flush()
    return result


def _post_card(post: dict, paste_mode: bool) -> str:
    """单帖卡片：左边色条+银行标签+分类副标+标题+数据行+点评气泡+按钮式原帖链接。

    热门榜单项与正文卡片复用点评和原帖链接，避免公众号粘贴版丢失关键信息。
    """
    color = _bank_color(post["bank"])
    bank = _esc(post["bank"])

    # 仅在无法匹配正文详情时保留精简榜单行。
    if post.get("is_list_item") and not post.get("note") and not post.get("url"):
        title = _esc(post["title"])
        replies = post["replies"]
        views = post["views"]
        replies_str = f"{replies}" if replies != "?" else "?"
        views_str = f"{views}" if views != "?" else "?"
        rank = post.get("rank", "")
        rank_html = (
            f'<span style="display:inline-block;min-width:22px;font-size:13px;font-weight:700;'
            f'color:{color};text-align:center">{rank}</span>'
        ) if rank else ""
        bank_tag = (
            f'<span style="display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;'
            f'border-radius:4px;color:#fff;background:{color};margin-left:8px">{bank}</span>'
        )
        title_html = title
        if post.get("url"):
            title_html = f'<a href="{_esc(post["url"])}" style="color:#0f172a;text-decoration:none">{title}</a>'
        return (
            f'<div style="position:relative;background:#f8fafc;border-radius:8px;padding:10px 14px 10px 16px;'
            f'margin-bottom:8px;border:1px solid #e5e7eb;overflow:hidden">'
            f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{color}"></div>'
            f'<div style="display:flex;align-items:center;gap:0">'
            f'{rank_html}<span style="font-size:14px;font-weight:600;color:#0f172a;line-height:1.4;margin-left:6px;flex:1">{title_html}</span>{bank_tag}'
            f'</div>'
            f'<div style="font-size:11px;color:#94a3b8;margin-top:4px;margin-left:28px">{replies_str} 条回复 · {views_str} 次阅读</div>'
            f'</div>'
        )

    summary = _esc(post["summary"])
    original_title = post["title"]
    # 详情卡优先展示 Markdown 卡头的一句话摘要；完整原标题保留在原帖链接汇总中。
    display_title = post["summary"].strip() or original_title
    title = _esc(display_title)
    replies = post["replies"]
    views = post["views"]
    replies_str = f"{replies}" if replies != "?" else "?"
    views_str = f"{views}" if views != "?" else "?"

    # 银行标签
    bank_tag = f'<span style="display:inline-block;font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;color:#fff;background:{color}">{bank}</span>'
    # 分类副标签（如有）
    sub_tag = ""
    if post.get("tag_label"):
        sub_tag = f'<span style="display:inline-block;font-size:10px;font-weight:600;padding:2px 6px;border-radius:4px;color:{color};background:#fff">{_esc(post["tag_label"])}</span>'
    sub_row = f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">{bank_tag}{sub_tag}</div>' if sub_tag else f'<div style="margin-bottom:4px">{bank_tag}</div>'

    # 数据行
    stats = f"{replies_str} 条回复 · {views_str} 次阅读"
    stats_html = f'<div style="font-size:12px;color:#94a3b8;margin-top:3px">{stats}</div>'

    # 点评气泡（缺失时 fallback 套话）
    note = post.get("note") or ""
    if not note and gen_editor_note is not None:
        try:
            ns, nf = gen_editor_note(post)
            note = ns + (" → " + nf if nf else "")
        except Exception:
            note = ""
    if not note:
        note = "「" + (post["title"] or summary) + "」见原帖讨论。"
    note_html = (
        f'<div style="font-size:12px;color:#1e293b;margin-top:8px;padding:8px 10px;'
        f'background:#fff;border:1px solid #e5e7eb;border-radius:6px;line-height:1.6">'
        f'<span style="color:{color};font-weight:700">📝 编辑点评：</span>{_esc(note)}</div>'
    )

    # 原帖链接：粘贴版用纯文本 URL，预览版用 <a>
    url = post.get("url", "")
    if paste_mode:
        link_html = (
            f'<div style="margin-top:6px;font-size:11px;color:#94a3b8;word-break:break-all">'
            f'🔗 原帖 {_esc(url)}</div>'
        ) if url else ""
    else:
        link_html = (
            f'<div style="margin-top:8px"><a href="{_esc(url)}" style="display:inline-block;'
            f'font-size:11px;font-weight:600;color:{color};padding:3px 10px;border:1px solid {color};'
            f'border-radius:4px;text-decoration:none">🔗 查看原帖</a></div>'
        ) if url else ""

    return (
        f'<div style="position:relative;background:#f8fafc;border-radius:8px;padding:12px 14px 12px 16px;'
        f'margin-bottom:10px;border:1px solid #e5e7eb;overflow:hidden">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;background:{color}"></div>'
        f'{sub_row}'
        f'<div style="font-size:15px;font-weight:600;color:#0f172a;line-height:1.4;'
        f'overflow-wrap:anywhere;word-break:break-word;margin-top:2px">💬 {title}</div>'
        f'{stats_html}{note_html}{link_html}</div>'
    )


def _section_block(section: dict, paste_mode: bool) -> str:
    """板块块：标题 + 帖子卡片列表 或 空板块占位。"""
    icon = SECTION_ICON.get(section["name"], "")
    head = (
        f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;'
        f'padding-left:10px;border-left:3px solid #6366f1">{icon} {section["name"]}</p>'
    )
    if section.get("empty") or not section["posts"]:
        return head + '<div style="font-size:12px;color:#94a3b8;padding:8px 14px;background:#f8fafc;border-radius:8px;margin-bottom:10px">（本日无相关讨论）</div>'
    # 榜单板块：给每个 list_item 灌排名序号
    posts = section["posts"]
    if any(p.get("is_list_item") for p in posts):
        for idx, p in enumerate(posts, 1):
            if p.get("is_list_item"):
                p["rank"] = f"NO.{idx}"
    cards = "".join(_post_card(p, paste_mode) for p in posts)
    return head + cards


def _visible_sections(daily: dict) -> list[dict]:
    """Show hot items as a ranking only; do not repeat them in category cards."""
    hot_titles = set()
    for section in daily["sections"]:
        if "热门讨论" not in section["name"]:
            continue
        for post in section["posts"]:
            title = re.sub(r"\s+", "", (post.get("title") or post.get("summary") or "").strip())
            if title:
                hot_titles.add(title)
    visible = []
    for section in daily["sections"]:
        if "热门讨论" in section["name"]:
            visible.append(section)
            continue
        posts = []
        for post in section["posts"]:
            title = re.sub(r"\s+", "", (post.get("title") or post.get("summary") or "").strip())
            if title not in hot_titles:
                posts.append(post)
        if posts or not section["posts"]:
            visible.append(dict(section, posts=posts))
    return visible

def build_body(daily: dict, paste_mode: bool) -> str:
    """组装正文：今日概览 + 各板块 + CTA。"""
    parts = []

    # 今日概览
    meta = daily.get("meta", "")
    meta = _clean_category_stats(meta)
    parts.append(
        '<p style="font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;background:#f8f9fa;border-radius:8px;line-height:1.6">'
        f'📊 <strong>今日概览</strong> — {_esc(meta) or "精选日报"}</p>'
    )

    # 各板块；热门榜单中的帖子不在分类区重复展示。
    display_sections = _visible_sections(daily)
    for section in display_sections:
        parts.append(_section_block(section, paste_mode))

    # CTA
    if paste_mode:
        parts.append(
            '<div style="margin-top:24px;padding:16px;background:#0f172a;border-radius:10px;text-align:center;color:#fff">'
            '<p style="font-size:14px;font-weight:500;margin-bottom:4px">💬 你觉得今天哪条最有价值？评论区聊聊</p>'
            '<p style="font-size:13px;margin-top:8px">关注 <strong>飞客信用卡日报</strong></p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:2px">转发给需要的朋友，一起避坑省钱</p></div>'
        )
    else:
        parts.append(
            '<div style="margin-top:24px;padding:16px;background:#0f172a;border-radius:10px;text-align:center;color:#fff">'
            '<p style="font-size:14px;font-weight:500;margin-bottom:4px">💬 你觉得今天哪条最有价值？评论区聊聊</p>'
            '<p style="font-size:13px;margin-top:8px">关注 <strong>飞客信用卡日报</strong></p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:4px">每日获取信用卡圈最新情报 · 回复「讨论」获取完整攻略</p>'
            '<p style="font-size:11px;color:#94a3b8;margin-top:2px">转发给需要的朋友，一起避坑省钱</p>'
            '<p style="font-size:12px;margin-top:12px"><a href="https://bagget541541.github.io/flyertrss/" style="color:#818cf8;text-decoration:none">🌐 在线阅读完整日报</a></p></div>'
        )

    return "\n".join(parts)


def _build_subtitle(daily: dict) -> str:
    """Pick the two highest-value posts, falling back to simple-mode posts."""
    hot = next((s for s in daily["sections"] if "热门讨论" in s["name"]), None)
    candidates = hot["posts"] if hot else [
        post
        for section in daily["sections"]
        if "热门讨论" not in section["name"]
        for post in section["posts"]
    ]
    if not candidates:
        return "今日日报"

    # simple mode has no LLM value tags or ranking section. Match the existing
    # hot-list convention: replies first, then reads; keywords break ties.
    if hot is None:
        boosts = {
            "申请": 12, "活动": 12, "权益": 10, "积分": 10, "里程": 10,
            "免年费": 10, "新卡": 15, "放水": 12, "实测": 8,
        }

        def value_score(post: dict) -> float:
            def number(key: str) -> int:
                value = str(post.get(key, 0)).replace(",", "")
                match = re.search(r"\d+", value)
                return int(match.group()) if match else 0

            title = post.get("title") or post.get("summary") or ""
            return number("replies") * 100000 + number("views") + sum(
                weight for keyword, weight in boosts.items() if keyword in title
            ) / 100

        candidates = sorted(enumerate(candidates), key=lambda pair: (-value_score(pair[1]), pair[0]))
        candidates = [post for _, post in candidates]

    items = []
    for post in candidates:
        title = (post.get("title") or post.get("summary") or "").strip()
        title = re.sub(r"^原帖\s+", "", title).strip(" ：:，。！？!? ")
        if title and title not in items:
            items.append(title[:18].rstrip("，。！？!? "))
        if len(items) == 2:
            break
    return "｜".join(items) if items else "今日日报"


def _optimized_subtitle(md: str) -> str:
    """从日报的热门榜单或正文前两帖生成副标题。"""
    match = re.search(r"(?ms)^##\s+[^\n]*(?:今日焦点|热门讨论)[^\n]*\n(.*?)(?=^##\s+|\Z)", md)
    items = []
    if match:
        for line in match.group(1).splitlines():
            bold = re.match(r"^\s*\d+[.、]\s+\*\*(.+?)\*\*", line)
            if bold:
                item = bold.group(1).strip()
                if item and item not in items:
                    items.append(item[:18].rstrip("，。！？!? "))
                if len(items) == 2:
                    break
                continue
            item_match = re.match(r"^\s*\d+[.、]\s+(?:\*\*(.+?)\*\*|(.+?))(?:（[^）]+）)?(?:\s+\[[^]]+\])?(?:\s+https?://\S+)?\s*$", line)
            if not item_match:
                continue
            item = (item_match.group(1) or item_match.group(2) or "").strip()
            if not item:
                continue
            item = re.sub(r"\s+", " ", item).strip(" ：:，。！？!? ")
            if item and item not in items:
                items.append(item)
            if len(items) == 2:
                break

    # 部分日报的热门讨论区只有标题，正文帖子才是唯一可靠来源。
    if len(items) < 2:
        for line in re.findall(r"(?m)^###\s+(.+?)\s*$", md):
            item = re.sub(r"\s+", " ", line).strip(" ：:，。！？!? ")
            if item and item not in items:
                items.append(item)
            if len(items) == 2:
                break
    return "｜".join(items) if items else "今日日报"

def gen_outputs(daily: dict, out_dir: Path, paste_only: bool, source: str) -> int:
    ds = daily["date"] or date.today().isoformat()
    article_title = daily.get("article_title") or f"飞客晚报 | {ds}"
    subtitle = _optimized_subtitle(daily["markdown"]) if daily.get("optimized") else _build_subtitle(daily)
    desc = daily["meta"] or f"今日精选日报 {ds}"

    body_paste = build_optimized_body(daily) if daily.get("optimized") else build_body(daily, paste_mode=True)
    paste_html = (
        f'<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;'
        f"font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8\">"
        f'<div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{_esc(article_title)}</div>'
        f'<div style="font-size:13px;color:#999;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #eee">{ds} · 精选日报</div>'
        f'<div style="font-size:13px;color:#6366f1;margin-bottom:20px;line-height:1.5">{_esc(subtitle)}</div>'
        f'{body_paste}</div>'
    )
    fn_paste = out_dir / f"公众号粘贴版_{ds}.html"
    fn_paste.write_text(paste_html, encoding="utf-8")
    print(f"[OK] 粘贴版 -> {fn_paste}")

    if not paste_only:
        body_preview = build_optimized_body(daily) if daily.get("optimized") else build_body(daily, paste_mode=False)
        preview_html = (
            '<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">\n'
            f"<title>{_esc(article_title)}</title>\n"
            f'<meta name="description" content="{_esc(desc)}">\n'
            f"<style>{ARTICLE_CSS}</style>\n</head>\n<body>\n"
            f'<div style="max-width:640px;margin:0 auto;background:#fff;padding:20px 16px 30px;'
            f"font-family:'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.8\">"
            f'<div style="font-size:20px;font-weight:700;line-height:1.4;margin-bottom:8px;color:#1a1a1a">{_esc(article_title)}</div>'
            f'<div style="font-size:13px;color:#999;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid #eee">{ds} · 精选日报</div>'
        f'<div style="font-size:13px;color:#6366f1;margin-bottom:20px;line-height:1.5">{_esc(subtitle)}</div>'
            f'{body_preview}\n</div>\n</body>\n</html>'
        )
        fn_preview = out_dir / f"公众号文章_{ds}.html"
        fn_preview.write_text(preview_html, encoding="utf-8")
        print(f"[OK] 预览版 -> {fn_preview}")

    # 元数据
    if daily.get("optimized"):
        heading_matches = list(re.finditer(r"(?m)^##\s+(.+)$", daily["markdown"]))
        display_sections = []
        for idx, match in enumerate(heading_matches):
            name = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", match.group(1)).strip()
            end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(daily["markdown"])
            block = daily["markdown"][match.end():end]
            count = len(re.findall(r"(?m)^###\s+", block))
            if name == "今日焦点":
                count = len(re.findall(r"(?m)^\d+\.\s+", block))
            display_sections.append({"name": name, "posts": [None] * count})
        declared_total = re.search(r"共\s*(\d+)\s*条讨论", daily.get("meta", ""))
        total_posts = int(declared_total.group(1)) if declared_total else len(re.findall(r"(?m)^###\s+", daily["markdown"]))
    else:
        display_sections = _visible_sections(daily)
        total_posts = sum(len(s["posts"]) for s in display_sections)
    meta = {
        "title": article_title,
        "description": desc,
        "subtitle": subtitle,
        "date": ds,
        "edition": "精选日报",
        "total_posts": total_posts,
        "sections": [{"name": s["name"], "count": len(s["posts"])} for s in display_sections],
        "source": source,
    }
    fn_meta = out_dir / f"公众号元数据_{ds}.json"
    fn_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 元数据 -> {fn_meta}")

    print(f"\n{'='*45}")
    # Windows PowerShell 常以 GBK 输出，日志去掉标题中的 emoji 不影响 HTML 内容。
    print(f"[TITLE] {article_title.replace('📋', '')}")
    print(f"[POSTS] {total_posts} 条 / {len(display_sections)} 个板块")
    print(f"[NEXT] 打开 {fn_paste.name} 全选复制 -> 公众号编辑器粘贴")
    print(f"{'='*45}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="基于精选日报 DOCX 或 Markdown 底稿生成公众号粘贴 HTML"
    )
    ap.add_argument("input_path", help="精选日报 .docx、.md 或 .markdown 文件路径")
    ap.add_argument("--out-dir", default="_site", help="输出目录（默认 _site）")
    ap.add_argument("--paste-only", action="store_true", help="只出粘贴版")
    args = ap.parse_args()

    input_path = Path(args.input_path)
    if not input_path.exists():
        print(f"[-] 文件不存在: {input_path}", file=sys.stderr)
        return 1
    if input_path.suffix.lower() not in {".docx", ".md", ".markdown"}:
        print("[-] 仅支持 .docx、.md 和 .markdown 输入文件", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        md = extract_markdown(input_path)
    except (OSError, ValueError, ImportError) as exc:
        print(f"[-] 读取输入失败: {exc}", file=sys.stderr)
        return 2
    if not md.strip():
        print("[-] 输入内容为空，检查文件是否正常", file=sys.stderr)
        return 2

    daily = parse_daily(md)
    # Detail fetches can return a prompt page; keep authoritative listing stats as fallback.
    listing_path = input_path.parent.parent / "threads_filtered.json"
    if listing_path.exists():
        try:
            listing_rows = json.loads(listing_path.read_text(encoding="utf-8"))
            listing_stats = {
                str(row.get("tid")): row for row in listing_rows if row.get("tid")
            }
            for section in daily["sections"]:
                for post in section["posts"]:
                    match = re.search(r"tid=(\d+)", post.get("url", ""))
                    row = listing_stats.get(match.group(1)) if match else None
                    if not row:
                        continue
                    if str(post.get("replies", "?")) in {"", "?"} and str(row.get("replies", "")).isdigit():
                        post["replies"] = str(row["replies"])
                    if str(post.get("views", "?")) in {"", "?"} and str(row.get("views", "")).isdigit():
                        post["views"] = str(row["views"])
        except (OSError, ValueError, TypeError):
            pass
    if daily.get("optimized"):
        detail_file = input_path.parent / f"threads_detail_{daily['date'][5:7]}{daily['date'][8:10]}.json"
        if detail_file.exists():
            try:
                detail_rows = json.loads(detail_file.read_text(encoding="utf-8"))
                daily["thread_stats"] = {
                    str(row.get("tid")): {
                        "replies": row.get("replies", "?"),
                        "views": row.get("views", "?"),
                        "url": row.get("url", ""),
                    }
                    for row in detail_rows if row.get("tid")
                }
                print(f"[OK] 回填帖子数据 -> {detail_file.name}")
            except (OSError, ValueError, TypeError) as exc:
                print(f"[!] 帖子数据回填跳过: {exc}", file=sys.stderr)
    if not daily["date"]:
        daily["date"] = date.today().isoformat()
        print(f"[!] 未解析到日期，用今天: {daily['date']}", file=sys.stderr)
    if not daily["sections"]:
        print("[-] 未解析到任何板块，检查底稿格式", file=sys.stderr)
        return 3

    source = "markdown" if input_path.suffix.lower() in {".md", ".markdown"} else "docx"
    return gen_outputs(daily, out_dir, args.paste_only, source)


if __name__ == "__main__":
    sys.exit(main())
