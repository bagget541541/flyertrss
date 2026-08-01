#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_daily_gen.py — 链接列表 → LLM 点评/归类/排版 → 技能格式 md

输入：output/links_MMDD.json（extract_links.py 产物，仅标题+URL）
输出：output/精选日报_MMDD-副标题.md（flyert-card-forum 技能格式）

LLM 配置：从 apikey.txt 读取（第1行 api_key，第2行 api_base），
          model 默认 mimo-v2-pro，可用 --model 覆盖。

流程（微信发布.bat 第 2 步）：
  链接列表 → LLM（skill 能力：点评/归类/排版）→ 技能格式 md
  可选：--html 传入当天预览版 HTML，按 tid 回填回复/阅读数（📊 行）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import httpx
except ImportError:
    print("[-] 需要 httpx：pip install httpx", file=sys.stderr)
    sys.exit(2)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

APIKEY_FILE = Path("apikey.txt")
DEFAULT_MODEL = "mimo-v2-pro"
DEFAULT_PROXY = "http://127.0.0.1:10808"
# 非聊天模型黑名单（模型探测时排除图像/视频/音频等）
NON_CHAT_KW = ("image", "video", "audio", "embedding", "tts", "whisper",
               "dall", "rerank", "vision")
# 低成本/低端关键词（优先调用，本任务较简单，低端模型即可胜任）
CHEAP_KW = ("flash", "mini", "lite", "light", "small", "nano", "fast",
            "turbo", "haiku", "3.5", "2.5", "2.0")
# 高端/昂贵关键词（最后才考虑）
PRICEY_KW = ("pro", "max", "ultra", "alpha", "beta", "sol", "opus",
             "sonnet", "large", "premium", "top")

SYSTEM_PROMPT = """你是飞客信用卡论坛的日报编辑。用户给你一批论坛原帖链接（标题+URL），
请你逐条完成三件事：

1. 点评：为每条写一段点评，按「现象 / 判断 / 依据」三段式组织，每段都是完整句子：
   ① 现象：帖子里发生了什么（具体卡种、权益变化、门槛条件、规则细节）；
   ② 判断：对持卡人的实际影响、值不值得参与、有什么坑；
   ③ 依据：引用帖子原文细节或论坛反馈支撑判断，不写空话套话。
   格式示例：
   💬 点评：现象：建行龙积分入账后自动按3:1兑换万象星。判断：万象星换京东卡约350:1实际收益不亮眼，只适合做火种或消费达标凑数。依据：论坛实测反馈该卡不值得专门多办一张。
   注意：三条之间用「现象：」「判断：」「依据：」显式标注，整体仍是一段连续文字。
2. 归类：把每条归入一个分类板块，可选分类：
   新卡发行 / 权益变更 / 停发退市 / 活动优惠 / 公告通知 / 疑问求助 / 用卡经验 / 其他
   活动类还要判断价值：🔴 高价值（无门槛/低门槛高回报）、🟡 中等、⚪ 套路。
3. 排版：按下面的 Markdown 格式输出完整日报。

输出要求（严格遵守）：
- 第一行：`# 飞客日报 📋 YYYY-MM-DD`（用当天日期）
- 概览行：`> 抓取时间 HH:MM | 共 N 条讨论 | 分类统计 | 数据源：flyert.com.cn 信用卡版块（原帖链接提取）`
- `## 🔥 热门讨论` 板块：列热度最高的 5 条，格式 `1. **帖子标题** [银行]`（不要写回阅数，不要括号）
- 其余板块按「新卡发行 → 权益变更 → 停发退市 → 活动优惠 → 公告通知 → 疑问求助 → 用卡经验 → 其他」顺序
- 每条帖子：
  ```
  ### 银行名 一句话摘要
  - 🔗 帖子标题：完整URL
  - 💬 点评：完整点评
  ```
  🔗 行直接写帖子标题原文（不要加"标题："字样），冒号后跟完整 URL
  活动板块在 ### 行尾加价值 emoji（如 `### 建设银行 线上积分 🟡`）
- 银行名从标题推断（建行→建设银行、招行→招商银行等），标题无法推断就写「其他」
- 全文不出现发帖人昵称；每条必须保留原文链接；不编造回复数/阅读数
- 只输出 Markdown 正文，不要 ``` 围栏，不要解释。"""


def load_llm_configs() -> list[dict]:
    """从 apikey.txt 读多组 (key, base)。key 行以 sk- 开头，下一行为 base。

    格式示例（每组两行，可多组）：
        sk-xxxx
        https://api.example.com/v1
        sk-yyyy
        https://api.another.com
    """
    if not APIKEY_FILE.exists():
        print(f"[-] 缺少 {APIKEY_FILE}（每组两行：api_key / api_base）", file=sys.stderr)
        sys.exit(2)
    lines = [ln.strip() for ln in APIKEY_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    groups: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith(("sk-", "sk_")):
            key = lines[i]
            base = lines[i + 1] if i + 1 < len(lines) else ""
            if base.startswith("http"):
                groups.append({"key": key, "base": base})
            i += 2
        else:
            i += 1
    if not groups:
        print("[-] apikey.txt 格式错误：需要 api_key / api_base 成对出现", file=sys.stderr)
        sys.exit(2)
    return groups


def _model_cost_rank(name: str) -> int:
    """低成本优先排序得分：低端词加分，高端词减分，越高越优先。

    同档内（如 flash 系）版本号越高越优先（agnes-2.5-flash > agnes-2.0-flash），
    但任何低端模型仍排在 pro/max/ultra 等昂贵模型之前。
    """
    n = name.lower()
    score = 0
    for kw in CHEAP_KW:
        if kw in n:
            score += 2
    for kw in PRICEY_KW:
        if kw in n:
            score -= 3
    # 同档内版本号微调：2.5 → +0.05，2.0 → +0.00（不影响跨档排序）
    m = re.search(r"(\d+)\.(\d+)", n)
    if m:
        major, minor = int(m.group(1)), int(m.group(2))
        score += major * 0.1 + minor / 100
    return score


def probe_models(key: str, base: str, proxy: str | None,
                 timeout: int = 25) -> list[str]:
    """GET {base}/models，返回可用聊天模型 id 列表（排除图像/视频等）。

    返回列表已按「低成本优先」排序：flash/mini/lite 等轻量模型在前，
    pro/max/ultra 等昂贵模型在后，避免一上来就调用最贵的。
    """
    try:
        with httpx.Client(trust_env=False, timeout=timeout, proxy=proxy) as c:
            resp = c.get(f"{base.rstrip('/')}/models",
                         headers={"Authorization": f"Bearer {key}"})
        if resp.status_code != 200:
            return []
        data = resp.json()
        ids = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
        ids = [i for i in ids
               if i and not any(k in i.lower() for k in NON_CHAT_KW)]
        ids.sort(key=_model_cost_rank, reverse=True)
        return ids
    except Exception:
        return []


def build_prompt(links: list[dict], ds: str,
                 details: dict[str, dict] | None = None) -> str:
    """构造 LLM prompt。details: tid → {content 首楼内容}，用于点评依据。"""
    rows = []
    for i, it in enumerate(links, 1):
        line = f"{i+1}. {it['title']}  {it['url']}"
        tid = it.get("tid", "")
        if details and tid in details:
            content = (details[tid].get("content") or "").strip()
            if content:
                line += f"\n   帖子原文：{content[:400]}"
        rows.append(line)
    body = "\n\n".join(rows)
    return (f"今天是 {ds}。以下是今天论坛的原帖链接及部分帖子原文：\n\n"
            f"{body}\n\n请按规则输出完整日报。")


def call_llm(prompt: str, groups: list[dict], model_override: str | None,
             proxy: str | None = None, timeout: int = 180) -> str:
    """逐组调用：探测模型 → chat/completions，失败自动切下一组。

    返回 LLM 原始文本；全部失败返回 ""。
    """
    proxies = proxy or DEFAULT_PROXY
    for gi, g in enumerate(groups, 1):
        key, base = g["key"], g["base"]
        models = [model_override] if model_override else probe_models(key, base, proxies)
        if not models:
            print(f"[-] 组{gi} {base} 探测模型失败，尝试默认 {DEFAULT_MODEL}",
                  file=sys.stderr)
            models = [DEFAULT_MODEL]
        for model in models:
            print(f"[LLM] 组{gi}/{len(groups)} {base} model={model} ...")
            url = f"{base.rstrip('/')}/chat/completions"
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 8192,
            }
            for attempt in range(2):
                try:
                    with httpx.Client(trust_env=False, timeout=timeout, proxy=proxies) as client:
                        resp = client.post(url, headers={"Authorization": f"Bearer {key}"},
                                           json=payload)
                    if resp.status_code != 200:
                        print(f"[-] 组{gi} [{model}] HTTP {resp.status_code}: "
                              f"{resp.text[:200]}", file=sys.stderr)
                        if attempt == 0:
                            print("  重试...")
                            continue
                        break  # 换下一个模型/组
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"] or ""
                    if not raw:
                        raw = data["choices"][0]["message"].get("reasoning_content", "")
                    return raw.strip()
                except httpx.TimeoutException:
                    print(f"[-] 组{gi} [{model}] 请求超时 ({timeout}s) "
                          f"[{attempt+1}/2]", file=sys.stderr)
                    if attempt == 0:
                        print("  重试...")
                        continue
                    break
                except Exception as e:
                    print(f"[-] 组{gi} [{model}] 调用异常: {e}", file=sys.stderr)
                    if attempt == 0:
                        print("  重试...")
                        continue
                    break
    return ""


def strip_fences(raw: str) -> str:
    """去掉可能的 ```markdown ... ``` 围栏。"""
    m = re.search(r"```[a-zA-Z]*\s*\n(.*?)```", raw, re.DOTALL)
    return m.group(1).strip() if m else raw.strip()


def backfill_stats(md: str, html_path: Path | None) -> str:
    """按 tid 从预览版 HTML 卡片区回填 📊 回复/阅读行（可选增强）。"""
    if html_path is None or not html_path.exists() or BeautifulSoup is None:
        return md
    html = html_path.read_text(encoding="utf-8-sig")
    soup = BeautifulSoup(html, "html.parser")
    tid_stats: dict[str, tuple[str, str]] = {}
    for card in soup.find_all("div", style=lambda v: v and "position:relative;background:#f8fafc" in (v or "")):
        a = card.find("a", href=True)
        if not a:
            continue
        m = re.search(r"tid=(\d+)", a["href"])
        if not m:
            continue
        d = card.find("div", style=lambda v: v and "color:#94a3b8" in (v or ""))
        if not d:
            continue
        sm = re.match(r"(\d+)\s*条回复\s*[·•]\s*(\d+)\s*次阅读", d.get_text(strip=True))
        if sm:
            tid_stats[m.group(1)] = (sm.group(1), sm.group(2))
    if not tid_stats:
        return md

    def repl(mo):
        url = mo.group(0)
        m = re.search(r"tid=(\d+)", url)
        if m and m.group(1) in tid_stats:
            r, v = tid_stats[m.group(1)]
            return f"{url}\n- 📊 {r}回 / {v}阅"
        return url

    # 在每条 `- 🔗 标题：URL` 行后补 📊 行
    lines = md.splitlines()
    out = []
    for ln in lines:
        out.append(ln)
        m = re.match(r"^-\s*(?:🔗|📋)\s+.*?(https?://\S+)", ln)
        if m:
            url = m.group(1)
            tm = re.search(r"tid=(\d+)", url)
            if tm and tm.group(1) in tid_stats:
                r, v = tid_stats[tm.group(1)]
                out.append(f"- 📊 {r}回 / {v}阅")
    md = "\n".join(out)

    # 热门讨论榜单行补回阅数：`1. **标题** [银行]` -> `1. **标题**（N回/N阅）[银行]`
    title_stats = _stats_by_title(md, tid_stats)
    if title_stats:
        md = _backfill_hot_list(md, title_stats)
    return md


def _stats_by_title(md: str, tid_stats: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """从 md 详情卡 `- 🔗 标题：URL` + `- 📊 N回/N阅` 建标题→回阅数映射。"""
    mapping: dict[str, tuple[str, str]] = {}
    cur = None
    for ln in md.splitlines():
        m = re.match(r"^-\s*(?:🔗|📋)\s+(.+?)：\s*(https?://\S+)", ln)
        if m:
            cur = m.group(1).strip()
            tm = re.search(r"tid=(\d+)", m.group(2))
            if tm and tm.group(1) in tid_stats:
                mapping[cur] = tid_stats[tm.group(1)]
            continue
        sm = re.match(r"^-\s*📊\s*(\d+)\s*回\s*/\s*(\d+)\s*阅", ln)
        if sm and cur and cur not in mapping:
            mapping[cur] = (sm.group(1), sm.group(2))
    return mapping


def _backfill_hot_list(md: str, title_stats: dict[str, tuple[str, str]]) -> str:
    """给热门讨论榜单行补 `（N回/N阅）`，仅当行内还没有回阅数。"""
    out = []
    for ln in md.splitlines():
        m = re.match(r"^(\d+)[.、]\s*\*\*(.+?)\*\*(\s*\[[^\]]*\])?$", ln)
        if m:
            title = m.group(2).strip()
            tail = m.group(3) or ""
            # 用「（N回/」判定是否已有回阅数，避免标题含"回"字（如"9个回合"）误判
            if not re.search(r"（[\d.]+K?M?回/", ln) and title in title_stats:
                r, v = title_stats[title]
                ln = f"{m.group(1)}. **{title}**（{r}回/{v}阅）{tail}".rstrip()
        out.append(ln)
    return "\n".join(out)


def make_subtitle(md: str) -> str:
    """副标题 = 热门讨论第一条标题去掉尾部语气词。"""
    title = ""
    hot = re.search(r"##\s*🔥\s*热门讨论\s*\n(?:.*\n)*?(\d+)[.、]\s*\*\*(.+?)\*\*", md)
    if hot:
        title = hot.group(2).strip()
    if not title:
        m = re.search(r"- (?:🔗|📋)\s+(.+?)：https?://", md)
        if m:
            title = m.group(1).strip()
    sub = title.rstrip("啦吗呢啊吧哦呀！？。！?～~ ").strip()
    if len(sub) > 20:
        sub = sub[:20]
    return sub or "今日日报"


def main() -> int:
    ap = argparse.ArgumentParser(description="链接列表 → LLM 点评/归类/排版 → 技能格式 md")
    ap.add_argument("links_json", nargs="?", default=None,
                    help="output/links_MMDD.json（默认当天最新）")
    ap.add_argument("--out-dir", default="output", help="md 输出目录（默认 output）")
    ap.add_argument("--html", default=None,
                    help="当天预览版 HTML 路径（可选，用于回填回复/阅读数）")
    ap.add_argument("--detail", default=None,
                    help="threads_detail_MMDD.json 路径（可选，帖子首楼内容作点评依据；默认自动找最新）")
    ap.add_argument("--model", default=None, help="LLM 模型（默认自动探测各端点可用模型）")
    ap.add_argument("--proxy", default=None,
                    help=f"HTTP 代理（默认 {DEFAULT_PROXY}；传 none 禁用）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印发送给 LLM 的 prompt，不调用 LLM")
    ap.add_argument("--print-path", action="store_true",
                    help="成功时只打印输出 md 路径（供 bat 捕获）")
    args = ap.parse_args()

    # 链接列表
    links_path = Path(args.links_json) if args.links_json else None
    if links_path is None:
        cands = sorted(Path(args.out_dir).glob("links_*.json"))
        if not cands:
            print("[-] 未找到 links_*.json，先运行 extract_links.py", file=sys.stderr)
            return 1
        links_path = cands[-1]
    if not links_path.exists():
        print(f"[-] 链接列表不存在: {links_path}", file=sys.stderr)
        return 1
    links = json.loads(links_path.read_text(encoding="utf-8"))
    if not links:
        print("[-] 链接列表为空", file=sys.stderr)
        return 1

    ds = re.search(r"(\d{4})-(\d{2})-(\d{2})", links_path.name)
    ds = f"{datetime.now().year}-{ds.group(2)}-{ds.group(3)}" if ds else datetime.now().strftime("%Y-%m-%d")

    prompt = build_prompt(links, ds)
    if args.dry_run:
        print(prompt)
        return 0

    # 加载帖子详情（首楼内容）作为点评依据
    details: dict[str, dict] = {}
    detail_path = None
    if args.detail:
        detail_path = Path(args.detail)
    else:
        cands = sorted(Path(args.out_dir).glob("threads_detail_*.json"))
        if cands:
            detail_path = cands[-1]
    if detail_path and detail_path.exists():
        try:
            for it in json.loads(detail_path.read_text(encoding="utf-8")):
                if it.get("tid") and it.get("content"):
                    details[str(it["tid"])] = it
        except Exception as e:
            print(f"[!] 详情加载失败（忽略）: {e}", file=sys.stderr)
    if details:
        print(f"[OK] 已加载 {len(details)} 条帖子详情作点评依据")
        prompt = build_prompt(links, ds, details)
    else:
        print("[!] 未找到帖子详情，点评可能缺少原文依据（可先运行 fetch_threads_detail.py）",
              file=sys.stderr)

    groups = load_llm_configs()
    proxy = None if (args.proxy or "").lower() == "none" else args.proxy
    raw = call_llm(prompt, groups, args.model, proxy=proxy)
    if not raw:
        print("[-] LLM 未返回内容（全部配置组失败）", file=sys.stderr)
        return 2
    md = strip_fences(raw)

    # 格式自检：必须有日期标题、板块、🔗 链接
    if not re.search(r"^#\s*飞客日报\s*📋?\s*\d{4}-\d{2}-\d{2}", md):
        md = f"# 飞客日报 📋 {ds}\n\n{md}"
    if "## " not in md or "🔗" not in md:
        print("[-] LLM 输出缺少板块或链接，格式异常，前 500 字：", file=sys.stderr)
        print(md[:500], file=sys.stderr)
        return 2

    # 回填回复/阅读数（如提供 HTML）
    html_path = Path(args.html) if args.html else None
    md = backfill_stats(md, html_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mmdd = ds.replace("-", "")[4:]
    sub = make_subtitle(md)
    out_path = out_dir / f"精选日报_{mmdd}-{sub}.md"
    out_path.write_text(md + "\n", encoding="utf-8")

    if args.print_path:
        print(out_path)
    else:
        print(f"[OK] 已生成 -> {out_path}")
        n_posts = len(re.findall(r"^- (?:🔗|📋)", md, re.M))
        print(f"[OK] 链接 {len(links)} 条 | md 内帖子 {n_posts} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
