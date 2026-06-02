# -*- coding: utf-8 -*-
"""手机竖屏卡片图 v2 (3:4 | P0 优化: 统计栏+银行标签+热力条+底部CTA+紧凑排版)"""
import sys, os, json
from datetime import date
from pathlib import Path
from collections import Counter

cwd = Path(__file__).parent
os.chdir(str(cwd))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CARD_W, CARD_H = 1080, 1440
BRANDING = "@moat成长"
OUT_DIR = cwd / "_cards"

PALETTES = {
    "hot":      {"accent":"#dc2626","bg":"#fef2f2","fg":"#991b1b","bar":"#fca5a5"},
    "农行":     {"accent":"#16a34a","bg":"#f0fdf4","fg":"#166534","bar":"#86efac"},
    "股份行":   {"accent":"#2563eb","bg":"#eff6ff","fg":"#1e40af","bar":"#93c5fd"},
    "国有行":   {"accent":"#7c3aed","bg":"#f5f3ff","fg":"#5b21b6","bar":"#c4b5fd"},
    "速览":     {"accent":"#78716c","bg":"#f5f5f4","fg":"#44403c","bar":"#d6d3d1"},
}

CSS = """\
* {{ margin:0; padding:0; box-sizing:border-box; }}
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700;900&family=Instrument+Sans:wght@400;500;600;700;800&display=swap');
body {{
  width: {w}px; height: {h}px;
  font-family: "Instrument Sans","PingFang SC","Microsoft YaHei",sans-serif;
  background: #f3f4f6; display:flex; flex-direction:column;
  position:relative; overflow:hidden;
}}
body::before {{
  content:""; position:absolute; inset:0;
  background:radial-gradient(circle at 80% 10%,rgba(99,102,241,0.04) 0%,transparent 50%);
  pointer-events:none; z-index:0;
}}

.header {{
  flex-shrink:0; position:relative; z-index:1;
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 60%,#0f172a 100%);
  color:#fff; padding:34px 28px 22px;
}}
.header h1 {{
  font-family:"Noto Serif SC",serif;
  font-size:26px; font-weight:900;
}}
.header h1 span {{ color:#fbbf24; }}
.header .sub {{
  display:flex; align-items:center; gap:8px;
  margin-top:4px; font-size:12px; color:#94a3b8;
}}

.stats {{
  flex-shrink:0; position:relative; z-index:1;
  display:flex; justify-content:space-around;
  padding:12px 20px;
  background:#fff; border-bottom:1px solid #e5e7eb;
}}
.stat-item {{ text-align:center; }}
.stat-item .num {{ font-size:18px; font-weight:800; color:{accent}; }}
.stat-item .lab {{ font-size:10px; color:#94a3b8; margin-top:1px; letter-spacing:0.3px; }}

.content {{
  flex:1; position:relative; z-index:1;
  padding:14px 20px 8px; overflow-y:auto;
}}

.post {{
  background:#fff; border-radius:10px; padding:12px 16px; margin-bottom:10px;
  box-shadow:0 1px 2px rgba(0,0,0,0.04); position:relative; overflow:hidden;
}}
.post .left-bar {{
  position:absolute; left:0; top:0; width:4px; height:100%;
  background:{accent}; border-radius:10px 0 0 10px;
}}
.post .title {{
  font-size:15px; font-weight:600; color:#0f172a;
  line-height:1.5; margin-bottom:5px; padding-right:60px;
}}
.post .tag {{
  position:absolute; top:12px; right:12px;
  font-size:10px; font-weight:600; color:{accent};
  background:{bar}; padding:1px 8px; border-radius:4px;
  max-width:56px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.post .meta {{
  display:flex; align-items:center; gap:12px;
  font-size:12px; color:#94a3b8;
}}
.post .meta .replies {{ color:{accent}; font-weight:700; }}
.post .heat-track {{
  flex:1; height:4px; background:#e5e7eb; border-radius:2px;
  max-width:80px; overflow:hidden;
}}
.post .heat-fill {{
  height:100%; background:{accent}; border-radius:2px;
}}

.hot-title::before {{
  content:"HOT "; font-size:10px; font-weight:800;
  color:#fff; background:#dc2626;
  padding:1px 6px; border-radius:3px; margin-right:4px;
}}

.compact .post {{ padding:9px 12px; margin-bottom:6px; }}
.compact .post .title {{ font-size:13px; padding-right:50px; }}
.compact .post .tag {{ font-size:9px; top:9px; right:9px; max-width:48px; }}

.footer {{
  flex-shrink:0; position:relative; z-index:1; text-align:center;
  padding:14px 0 20px;
  background:linear-gradient(0deg,#fff 0%,transparent 100%);
}}
.footer .sect {{
  font-family:"Noto Serif SC",serif;
  font-size:14px; font-weight:700; color:{accent};
}}
.footer .cta {{
  font-size:12px; color:#6366f1; font-weight:600; margin-top:3px;
}}"""

TPL = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<style>""" + CSS + """</style></head><body>
<div class="header">
  <h1>飞客<span>信用卡</span>日报</h1>
  <div class="sub"><span>{ds}</span><span>|</span><span>{bank_count} 家银行 · {total} 条</span></div>
</div>
<div class="stats">
  <div class="stat-item"><div class="num">{top_replies}</div><div class="lab">最高回复</div></div>
  <div class="stat-item"><div class="num">{bank_count}</div><div class="lab">覆盖银行</div></div>
  <div class="stat-item"><div class="num">{hot_bank}</div><div class="lab">最多讨论</div></div>
</div>
<div class="content{extra_cls}">{posts_html}</div>
<div class="footer">
  <div class="sect">{section}</div>
  <div class="cta">关注 {branding} 每日获取信用卡情报</div>
</div>
</body></html>"""


def _render_card(posts, ds, total, palette, idx, section, branding,
                 bank_count, hot_bank, top_replies, compact=False):
    """渲染一张卡片"""
    max_r = max((t.get("replies", 0) for t in posts), default=1)

    posts_html = []
    for t in posts:
        r = t.get("replies", 0)
        title = t.get("title", "")
        author = t.get("author", "")
        cat = t.get("category", "")
        pct = min(r / max_r * 100, 100) if max_r > 0 else 0
        is_hot = r >= 20
        title_cls = ' class="hot-title"' if is_hot else ""
        tag_html = f'<span class="tag">{cat}</span>' if cat else ""
        posts_html.append(
            '<div class="post">'
            f'<div class="left-bar"></div>'
            f'{tag_html}'
            f'<div{title_cls}>{title}</div>'
            f'<div class="meta">'
            f'<span class="replies">{r} 回复</span>'
            f'<span>{author}</span>'
            f'<div class="heat-track"><div class="heat-fill" style="width:{pct:.0f}%"></div></div>'
            f'</div></div>'
        )

    posts_joined = "\n".join(posts_html)

    hot_bank_short = hot_bank[:2] if len(hot_bank) > 4 else hot_bank

    tmp = cwd / f"__card_{idx}.html"
    html = TPL.format(
        w=CARD_W, h=CARD_H,
        accent=palette["accent"],
        fg=palette["fg"],
        bar=palette["bar"],
        ds=ds,
        total=total,
        bank_count=bank_count,
        top_replies=top_replies,
        hot_bank=hot_bank_short,
        posts_html=posts_joined,
        section=section,
        branding=branding,
        extra_cls=" compact" if compact else "",
    )
    tmp.write_text(html, encoding="utf-8")
    out = OUT_DIR / f"card_{idx:02d}.png"

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(out), full_page=True)
            browser.close()
        return True, out
    except Exception as e:
        return False, str(e)
    finally:
        if tmp.exists(): tmp.unlink()


def _int(v):
    try: return int(v)
    except: return 0


def _fmt_bank_name(name):
    """缩短银行名: '中国农业银行' -> '农业银行'"""
    for prefix in ["中国"]:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def main():
    data_path = cwd / "threads_filtered.json"
    if not data_path.exists():
        print("[-] 没有数据文件, 先跑 fetcher.py")
        return
    with open(data_path, encoding="utf-8") as f:
        threads = json.load(f)
    if not threads:
        print("[-] 数据为空")
        return

    for t in threads:
        t["replies"] = _int(t.get("replies", 0))
        t["views"] = _int(t.get("views", 0))
        t["category"] = _fmt_bank_name(t.get("category", ""))

    ds = date.today().isoformat()
    total = len(threads)
    OUT_DIR.mkdir(exist_ok=True)

    # 全局统计
    all_banks = [t.get("category", "其他") for t in threads]
    bank_counter = Counter(all_banks)
    bank_count = len(bank_counter)
    hot_bank = bank_counter.most_common(1)[0][0] if bank_counter else "—"
    top_replies = max(t["replies"] for t in threads)

    # 按回复数降序
    threads.sort(key=lambda t: -t["replies"])

    # 分组
    hot = threads[:6]
    remaining = [t for t in threads if t not in hot]
    banks = {}
    for t in remaining:
        b = t.get("category", "其他")
        banks.setdefault(b, []).append(t)

    agri = banks.pop("农业银行", [])[:6]
    joint_stock = []
    for b in ["招商银行", "交通银行", "浦发银行", "平安银行", "兴业银行"]:
        if b in banks:
            joint_stock.extend(banks.pop(b))
    joint_stock.sort(key=lambda t: -t["replies"])

    others = []
    for b in list(banks.keys()):
        others.extend(banks.pop(b))
    others.sort(key=lambda t: -t["replies"])

    all_compact = threads[:8]

    cards_data = [
        ("hot",   "今日热门",   hot,         PALETTES["hot"]),
        ("农行",   "农业银行",   agri,        PALETTES["农行"]),
        ("股份行", "股份行精选", joint_stock, PALETTES["股份行"]),
        ("其他",   "更多讨论",   others,      PALETTES["速览"]),
        ("速览",   "全量速览",   all_compact, PALETTES["国有行"]),
    ]

    idx = 0
    ok_count = 0
    for key, name, posts, palette in cards_data:
        if not posts:
            continue
        idx += 1
        compact = (key == "速览")
        print(f"[{idx}] {name} ({len(posts)} 条)...", end=" ", flush=True)
        ok, res = _render_card(
            posts, ds, total, palette, idx, name, BRANDING,
            bank_count, hot_bank, top_replies, compact=compact,
        )
        if ok:
            ok_count += 1
            print(f"OK -> {res.name}")
        else:
            print(f"FAIL: {res}")

    print(f"\n完成! {ok_count} 张 -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
