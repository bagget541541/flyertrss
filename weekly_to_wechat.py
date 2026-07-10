#!/usr/bin/env python3
"""
weekly_to_wechat.py — 基于周报 Markdown 生成公众号粘贴 HTML

输入：Weekly_Report_YYYY年M月第N周.md（结构化周报）
输出：
  公众号粘贴版_{周报标识}.html   纯内联片段，粘贴进公众号编辑器
  公众号元数据_{周报标识}.json   元数据

周报结构：
  # 信用卡周报 - 2026年7月第2周
  ## 🔄 权益变更 / ## 🏷️ 活动 / ...
  ### {标题}                    卡片头
  **亮点：** xxx
  银行：xxx | 来源：xxx
  [原文链接](url)
  **结构化信息：**
  - **键**：值
  ...
  **原文摘要：**
  ...

视觉模板复用 docx_to_wechat.py：左边色条 + 银行标签 + 标题 + 数据行 + 卡片正文。
约束：公众号粘贴只认内联 style，禁用 <style>/JS/外部资源/外部字体/class。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ── 银行→主色 映射 ────────────────────────────────────────────────
BANK_COLOR = {
    "工商银行": "#dc2626", "工行": "#dc2626", "工银": "#dc2626",
    "汇丰银行": "#ea580c", "汇丰": "#ea580c", "比丰": "#ea580c",
    "中信银行": "#2563eb", "中信": "#2563eb",
    "农行": "#16a34a", "农业银行": "#16a34a", "老农": "#16a34a",
    "交通银行": "#7c3aed", "交行": "#7c3aed", "沃德": "#7c3aed",
    "邮储银行": "#d97706", "邮储": "#d97706",
    "招商银行": "#db2777", "招行": "#db2777",
    "浦发银行": "#0d9488", "浦发": "#0d9488",
    "中国银行": "#475569", "中行": "#475569",
    "平安银行": "#059669", "平安": "#059669",
    "光大银行": "#9333ea", "光大": "#9333ea",
    "华夏银行": "#0ea5e9", "华夏": "#0ea5e9",
    "兴业银行": "#1d4ed8", "兴业": "#1d4ed8",
    "民生银行": "#f59e0b", "民生": "#f59e0b",
    "广发银行": "#be123c", "广发": "#be123c",
    "花旗银行": "#0891b2", "花旗": "#0891b2",
}
DEFAULT_BANK_COLOR = "#78716c"

# 板块图标（按板块名前缀匹配）
SECTION_ICONS = [
    ("权益变更", "⚠️"),
    ("活动", "🎁"),
    ("新卡", "🆕"),
    ("退发", "📉"),
    ("其他", "📌"),
    ("热门", "🔥"),
]


def _esc(s: str) -> str:
    """HTML 转义。"""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _bank_color(bank: str) -> str:
    """银行名 → 主色；未命中走默认灰。"""
    if not bank:
        return DEFAULT_BANK_COLOR
    if bank in BANK_COLOR:
        return BANK_COLOR[bank]
    # 前缀模糊匹配
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if bank.startswith(name) or name.startswith(bank):
            return BANK_COLOR[name]
    return DEFAULT_BANK_COLOR


def _normalize_bank(raw: str) -> str:
    """银行字段归一到短名：'华夏银行' → '华夏'，'农业银行活动' → '农行'。"""
    if not raw:
        return ""
    raw = raw.strip()
    # 先精确命中
    if raw in BANK_COLOR:
        return raw
    # 前缀命中（长键优先）
    for name in sorted(BANK_COLOR.keys(), key=len, reverse=True):
        if raw.startswith(name):
            # 归一到短名：取同色组里最短的
            color = BANK_COLOR[name]
            short = min(
                (k for k, v in BANK_COLOR.items() if v == color),
                key=len,
            )
            return short
    return raw


def _section_icon(name: str) -> str:
    """板块名 → emoji。"""
    clean = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", name)
    for key, icon in SECTION_ICONS:
        if key in clean:
            return icon
    return "📌"


def parse_weekly(md: str) -> dict:
    """把周报 markdown 解析成 {title, period, sections:[{name, posts:[...]}]}。

    每个 post 结构：
      {title, highlight, bank, source, url, info:[{key,val}], summary}
    """
    lines = md.splitlines()
    weekly = {"title": "", "period": "", "sections": []}

    # 顶层标题：# 信用卡周报 - 2026年7月第2周
    for line in lines:
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            full = m.group(1).strip()
            weekly["title"] = full
            # 提取期次：2026年7月第2周
            mp = re.search(r"(\d{4}年\d+月第\d+周)", full)
            if mp:
                weekly["period"] = mp.group(1)
            break

    # 板块解析
    cur_section: dict | None = None
    cur_post: dict | None = None
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 一级板块
        m1 = re.match(r"^##\s+(.+)$", stripped)
        if m1:
            # 落尾
            if cur_post and cur_section:
                cur_section["posts"].append(cur_post)
                cur_post = None
            if cur_section:
                weekly["sections"].append(cur_section)
            name = m1.group(1).strip()
            cur_section = {"name": name, "posts": []}
            i += 1
            continue

        # 三级卡片头
        m3 = re.match(r"^###\s+(.+)$", stripped)
        if m3 and cur_section is not None:
            if cur_post:
                cur_section["posts"].append(cur_post)
            cur_post = {
                "title": m3.group(1).strip(),
                "highlight": "",
                "bank": "",
                "source": "",
                "url": "",
                "info": [],
                "summary": "",
            }
            i += 1
            continue

        # 卡片体内字段
        if cur_post is not None:
            # 亮点
            mh = re.match(r"^\*\*亮点[：:]\*\*\s*(.*)$", stripped)
            if mh:
                cur_post["highlight"] = mh.group(1).strip()
                i += 1
                continue
            # 银行 + 来源
            mb = re.match(
                r"^银行[：:]\s*(.+?)\s*\|\s*来源[：:]\s*(.+)$", stripped
            )
            if mb:
                cur_post["bank"] = _normalize_bank(mb.group(1).strip())
                cur_post["source"] = mb.group(2).strip()
                i += 1
                continue
            # 原文链接
            ml = re.match(r"^\[原文链接\]\((https?://[^\s)]+)\)$", stripped)
            if ml:
                cur_post["url"] = ml.group(1).strip()
                i += 1
                continue
            # 结构化信息块开始
            if stripped == "**结构化信息：**":
                i += 1
                # 收集后续列表项，直到遇到 **原文摘要：** 或空板块/下一卡
                while i < n:
                    li = lines[i].strip()
                    if li == "**原文摘要：**":
                        cur_post["_saw_summary"] = True
                        i += 1
                        break
                    if li.startswith("**") and li.endswith("**"):
                        # 另一个 **xxx：** 块，停止
                        break
                    # 列表项：- **键**：值 / - 值
                    mi = re.match(r"^-\s+(.*)$", li)
                    if mi:
                        body = mi.group(1).strip()
                        mk = re.match(
                            r"^\*\*(.+?)[：:]\*\*\s*(.*)$", body
                        )
                        if mk:
                            cur_post["info"].append(
                                {"key": mk.group(1).strip(), "val": mk.group(2).strip()}
                            )
                        else:
                            cur_post["info"].append(
                                {"key": "", "val": body}
                            )
                        i += 1
                        continue
                    # 非列表、非标记 → 结束 info 收集
                    break
                continue
            # 原文摘要块
            if stripped == "**原文摘要：**":
                i += 1
                summary_lines = []
                while i < n:
                    li = lines[i].strip()
                    if li == "---" or li.startswith("### "):
                        break
                    if li.startswith("**") and li.endswith("**"):
                        break
                    if li:
                        summary_lines.append(li)
                    i += 1
                cur_post["summary"] = "\n".join(summary_lines)
                continue
        i += 1

    # 落尾
    if cur_post and cur_section:
        cur_section["posts"].append(cur_post)
    if cur_section:
        weekly["sections"].append(cur_section)

    return weekly


def _render_post_card(post: dict) -> str:
    """单卡片：左边色条 + 银行标签 + 标题 + 亮点 + 结构化信息 + 原文链接。"""
    color = _bank_color(post["bank"])
    bank = _esc(post["bank"])
    title = _esc(post["title"])
    highlight = _esc(post["highlight"])

    # 银行标签行
    bank_tag = (
        f'<span style="display:inline-block;font-size:10px;font-weight:700;'
        f'padding:2px 8px;border-radius:4px;color:#fff;background:{color}">'
        f"{bank}</span>"
    ) if bank else ""
    source_tag = (
        f'<span style="display:inline-block;font-size:10px;font-weight:600;'
        f'padding:2px 6px;border-radius:4px;color:{color};background:#fff;'
        f'border:1px solid {color}">{_esc(post["source"])}</span>'
    ) if post["source"] else ""
    head_row = (
        f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">'
        f"{bank_tag}{source_tag}</div>"
    ) if (bank_tag or source_tag) else ""

    # 标题
    title_html = (
        f'<div style="font-size:15px;font-weight:600;color:#0f172a;'
        f'line-height:1.4;margin-top:2px">{title}</div>'
    )

    # 亮点
    highlight_html = ""
    if highlight:
        highlight_html = (
            f'<div style="font-size:12px;color:#1e293b;margin-top:6px;'
            f'padding:6px 8px;background:#fff;border:1px solid #e5e7eb;'
            f'border-radius:6px;line-height:1.6">'
            f'<span style="color:{color};font-weight:700">✨ 亮点：</span>'
            f"{highlight}</div>"
        )

    # 结构化信息列表
    info_html = ""
    info_items = post["info"]
    if info_items:
        info_rows = []
        for item in info_items:
            k = _esc(item["key"])
            v = _esc(item["val"])
            if k and v:
                info_rows.append(
                    f'<div style="font-size:12px;color:#334155;line-height:1.6;'
                    f'margin:2px 0"><span style="font-weight:600;color:#6366f1">'
                    f"{k}：</span>{v}</div>"
                )
            elif v:
                info_rows.append(
                    f'<div style="font-size:12px;color:#334155;line-height:1.6;'
                    f'margin:2px 0">{v}</div>'
                )
        if info_rows:
            info_html = (
                f'<div style="margin-top:6px;padding:6px 10px;background:#f8fafc;'
                f'border-radius:6px;border-left:3px solid {color}">'
                f'{"".join(info_rows)}</div>'
            )

    # 原文链接
    link_html = ""
    if post["url"]:
        link_html = (
            f'<div style="margin-top:6px;font-size:11px;color:#94a3b8;'
            f'word-break:break-all">🔗 原帖 {_esc(post["url"])}</div>'
        )

    return (
        f'<div style="position:relative;background:#f8fafc;border-radius:8px;'
        f'padding:12px 14px 12px 16px;margin-bottom:10px;border:1px solid #e5e7eb;'
        f'overflow:hidden">'
        f'<div style="position:absolute;left:0;top:0;bottom:0;width:4px;'
        f'background:{color}"></div>'
        f'{head_row}{title_html}{highlight_html}{info_html}{link_html}</div>'
    )


def _section_block(section: dict) -> str:
    """板块块：标题 + 卡片列表。"""
    icon = _section_icon(section["name"])
    head = (
        f'<p style="font-size:15px;font-weight:600;color:#333;margin-bottom:10px;'
        f'padding-left:10px;border-left:3px solid #6366f1">{icon} '
        f'{_esc(section["name"])}</p>'
    )
    if not section["posts"]:
        return head + (
            '<div style="font-size:12px;color:#94a3b8;padding:8px 14px;'
            'background:#f8fafc;border-radius:8px;margin-bottom:10px">'
            "（本期无相关内容）</div>"
        )
    cards = "".join(_render_post_card(p) for p in section["posts"])
    return head + cards


def build_body(weekly: dict) -> str:
    """组装正文：期次概览 + 各板块 + 原帖链接汇总 + AI 声明 + CTA。"""
    parts = []
    period = weekly.get("period", "")
    total = sum(len(s["posts"]) for s in weekly["sections"])

    # 期次概览
    overview = f"本期共 {total} 条动态"
    if period:
        overview = f"{period} · {overview}"
    parts.append(
        '<p style="font-size:14px;color:#666;margin-bottom:20px;padding:12px 14px;'
        f'background:#f8f9fa;border-radius:8px;line-height:1.6">'
        f'📊 <strong>周报概览</strong> — {_esc(overview)}</p>'
    )

    # 各板块
    for section in weekly["sections"]:
        parts.append(_section_block(section))

    # 原帖链接汇总
    link_list = []
    idx = 0
    for section in weekly["sections"]:
        for post in section["posts"]:
            url = post.get("url", "")
            if not url:
                continue
            idx += 1
            title = _esc(post["title"])
            link_list.append(
                f'<p style="font-size:12px;color:#6366f1;margin:3px 0;'
                f'word-break:break-all">{idx}. {title}<br>'
                f'<span style="font-size:11px;color:#94a3b8">'
                f'{_esc(url)}</span></p>'
            )
    if link_list:
        parts.append(
            '<div style="margin-top:24px;padding:14px 16px;background:#f8fafc;'
            'border-radius:10px;border:1px solid #e5e7eb">'
            '<p style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px">'
            f'🔗 原帖链接</p>{"".join(link_list)}</div>'
        )

    # AI 合规声明
    parts.append(
        '<div style="margin-top:12px;padding:8px 12px;background:#fff7ed;'
        'border-radius:6px;border:1px solid #fed7aa;text-align:center">'
        '<p style="font-size:11px;color:#9a3412;line-height:1.6">'
        "本内容由 AI 生成整理，请遵循相关法律法规及"
        "《人工智能生成合成内容标识办法》使用与传播。</p></div>"
    )

    # CTA
    parts.append(
        '<div style="margin-top:24px;padding:16px;background:#0f172a;'
        'border-radius:10px;text-align:center;color:#fff">'
        '<p style="font-size:14px;font-weight:500;margin-bottom:4px">'
        "💬 本期哪条权益/活动最值得关注？评论区聊聊</p>"
        '<p style="font-size:13px;margin-top:8px">关注 '
        "<strong>飞客信用卡周报</strong></p>"
        '<p style="font-size:11px;color:#94a3b8;margin-top:2px">'
        "转发给需要的朋友，一起避坑省钱</p></div>"
    )

    return "\n".join(parts)


def gen_outputs(weekly: dict, out_dir: Path) -> int:
    """生成粘贴版 HTML + 元数据 JSON。"""
    period = weekly.get("period", "周报")
    # 用期次做文件名标识：2026年7月第2周 → 2026年7月第2周
    ident = period if period else "周报"

    article_title = f"飞客周报 | {period}" if period else "飞客周报"
    body = build_body(weekly)
    paste_html = (
        f'<div style="max-width:640px;margin:0 auto;background:#fff;'
        f'padding:20px 16px 30px;font-family:\'PingFang SC\','
        f'\'Microsoft YaHei\',sans-serif;line-height:1.8">'
        f'<div style="font-size:20px;font-weight:700;line-height:1.4;'
        f'margin-bottom:8px;color:#1a1a1a">{_esc(article_title)}</div>'
        f'<div style="font-size:13px;color:#999;margin-bottom:20px;'
        f'padding-bottom:16px;border-bottom:1px solid #eee">'
        f'{_esc(ident)} · 信用卡周报</div>'
        f'{body}</div>'
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    fn_paste = out_dir / f"公众号粘贴版_{ident}.html"
    fn_paste.write_text(paste_html, encoding="utf-8")
    print(f"[OK] 粘贴版 -> {fn_paste}")

    # 元数据
    total_posts = sum(len(s["posts"]) for s in weekly["sections"])
    meta = {
        "title": article_title,
        "period": ident,
        "edition": "信用卡周报",
        "total_posts": total_posts,
        "sections": [
            {"name": s["name"], "count": len(s["posts"])}
            for s in weekly["sections"]
        ],
        "source": "weekly_md",
    }
    fn_meta = out_dir / f"公众号元数据_{ident}.json"
    fn_meta.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] 元数据 -> {fn_meta}")

    print(f"\n{'='*45}")
    print(f"📰 标题: {article_title}")
    print(f"📋 帖子: {total_posts} 条 / {len(weekly['sections'])} 个板块")
    print(f"💡 操作：打开 {fn_paste.name} 全选复制 → 公众号编辑器粘贴")
    print(f"{'='*45}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="基于周报 Markdown 生成公众号粘贴 HTML"
    )
    ap.add_argument("md", help="周报 Markdown 文件路径")
    ap.add_argument(
        "--out-dir", default="_site", help="输出目录（默认 _site）"
    )
    args = ap.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"[-] 文件不存在: {md_path}", file=sys.stderr)
        return 1

    md = md_path.read_text(encoding="utf-8")
    if not md.strip():
        print("[-] 文件内容为空", file=sys.stderr)
        return 2

    weekly = parse_weekly(md)
    if not weekly["period"]:
        print("[!] 未解析到期次，用文件名兜底", file=sys.stderr)
        weekly["period"] = md_path.stem
    if not weekly["sections"]:
        print("[-] 未解析到任何板块，检查周报格式", file=sys.stderr)
        return 3

    return gen_outputs(weekly, Path(args.out_dir))


if __name__ == "__main__":
    sys.exit(main())
