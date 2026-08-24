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

1. 点评：为每条写一段点评，包含三个层次但不加标签，整段话流畅连贯：
   ① 帖子里发生了什么（具体卡种、权益变化、门槛条件、规则细节）
   ② 对持卡人的实际影响、值不值得参与、有什么坑
   ③ 引用帖子原文细节或论坛反馈支撑判断，除非仅为帖子标题
   格式示例（不带标签，自然流畅）：
   💬 点评：建行龙积分入账后自动按3:1兑换万象星，万象星换京东卡约350:1实际收益不亮眼，只适合做火种或消费达标凑数。论坛实测反馈该卡不值得专门多办一张。
   注意：去掉「现象：」「判断：」「依据：」等标签，写成一段连续的自然段落。
   每条点评通常写 80-140 个中文字符，必须同时交代帖子事实、对持卡人的实际影响/价值或风险、以及帖子原文或回复中的具体依据；优先吸收回复区已经给出的规则、门槛、实测结果和操作路径，不要只复述标题，也不要用“建议咨询客服”“值得体验”“建议继续尝试”等空泛结论收尾。只有首楼和回复都没有有效信息时，才说明信息缺口，不得把未阅读回复区作为“信息不足”的理由。
   去 AI 味要求：直接写事实和判断，删掉“标志着、彰显、至关重要、持续演进、值得关注”等拔高或宣传性措辞；不用“业内人士认为”“有消息称”等模糊归因，引用必须来自给定帖子原文或明确写成信息不足。避免“这不仅是……更是……”式排比、硬凑三项并列、破折号转折和模板化的“未来可期”结尾。句子长短可以变化，但保持信用卡日报编辑的克制语气，不使用第一人称、聊天口吻、情绪化感叹或编造的个人体验。
   改写时必须保留卡种、活动门槛、比例、日期、金额和风险条件等可核实事实；没有原文支撑时宁可简短说明判断受限，也不得为增加文采补充细节。
2. 归类：把每条归入一个分类板块，可选分类：
   新卡发行 / 权益变更 / 停发退市 / 活动优惠 / 公告通知 / 疑问求助 / 用卡经验 / 其他
   分类优先级和边界：
   - 标题以提问、求助、咨询为主要目的时，优先归入「疑问求助」，即使内容涉及积分、权益、申卡或制卡。
   - 出现“多久到账/什么时候到账/未到账/没到账/怎么/如何/是否/是不是/能否/哪个/哪里/请教/咨询/求助/帮我看看/为什么/多久”等问句或求助表达，且不是明确的官方公告、活动规则发布或新卡发行公告时，归入「疑问求助」。
   - 「权益变更」只用于已经发生或被明确公告的权益调整、缩水、取消、规则变化，不用于询问权益到账、权益能否使用或持卡人求建议。
   - 「用卡经验」用于分享已经发生的刷卡、积分、里程或权益使用经历；如果标题主要是在问别人怎么办，仍归入「疑问求助」。
   活动类还要判断价值：🔴 高价值（无门槛/低门槛高回报）、🟡 中等、⚪ 套路。
3. 排版：按下面的 Markdown 格式输出完整日报。

输出要求（严格遵守）：
- 只输出最终 Markdown，不要输出思考过程、分析草稿、分类过程、重写过程、解释文字或多个版本；第一个字符必须是 `# 飞客日报`。
- 第一行：`# 飞客日报 📋 YYYY-MM-DD`（用当天日期）
- 概览行：`> 共 N 条讨论 | 分类统计 | 数据源：flyert.com.cn 信用卡版块`（只列出有内容的分类及其数量，不显示 0 条的分类；去掉抓取时间）
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
- 银行名优先使用每条链接后附带的 [板块：xxx]（这是论坛抓取的权威版块名，如「招商银行」「交通银行」）；没有 [板块：] 标注时再从标题推断（建行→建设银行、招行→招商银行等）；两者都无法确定就写「其他」。### 行首和热门榜 [银行] 必须与 [板块：] 一致，不得自行改写为其他银行
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
                 details: dict[str, dict] | None = None,
                 tid_category: dict[str, str] | None = None) -> str:
    """构造 LLM prompt。

    details: tid → {content 首楼内容}，用于点评依据。
    tid_category: tid → 权威板块（来自 threads_filtered/enriched 的 category，
        即论坛版块名，如「招商银行」）。喂给 LLM 让其直接用而非从标题推断。
    """
    tid_category = tid_category or {}
    rows = []
    for i, it in enumerate(links, 1):
        line = f"{i+1}. {it['title']}  {it['url']}"
        tid = str(it.get("tid", ""))
        cat = tid_category.get(tid, "")
        if cat:
            line += f"  [板块：{cat}]"
        if details and tid in details:
            content = (details[tid].get("content") or "").strip()
            if content:
                line += f"\n   帖子原文：{content[:1200]}"
            replies = details[tid].get("reply_samples") or []
            if replies:
                line += "\n   回复区摘要：" + " ｜ ".join(str(x)[:500] for x in replies[:6])
        rows.append(line)
    body = "\n\n".join(rows)
    return (f"今天是 {ds}。以下是今天论坛的原帖链接及部分帖子原文：\n\n"
            f"{body}\n\n请按规则输出完整日报。")


def load_tid_category(links: list[dict] | None = None) -> dict[str, str]:
    """加载权威板块映射 tid → category（论坛版块名，如「招商银行」）。

    优先当天 links 内的 category，再用 threads_enriched/filtered 补齐缺失 tid。
    均无时返回空 dict，调用方回退到 LLM 从标题推断。
    """
    mapping: dict[str, str] = {}
    direct_tids: set[str] = set()
    # 当天 links 是抓取链路的直接产物，优先于可能残留的历史 enriched 文件。
    for post in links or []:
        tid = str(post.get("tid", ""))
        cat = (post.get("category") or "").strip()
        if tid and cat:
            mapping[tid] = cat
            direct_tids.add(tid)
    if mapping:
        print(f"[OK] 已加载 {len(mapping)} 条当天链接板块映射")

    for fname in ("threads_enriched.json", "threads_filtered.json"):
        path = Path(fname)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            posts = data.get("posts", []) if isinstance(data, dict) else data
            for post in posts:
                tid = str(post.get("tid", ""))
                cat = (post.get("category") or "").strip()
                if tid and cat:
                    mapping.setdefault(tid, cat)
            if mapping:
                print(f"[OK] 已加载 {len(mapping)} 条权威板块映射 ({fname})")
                # 历史文件与当天链接匹配率过低时，不能把旧分类套到新帖子。
                link_tids = {str(x.get("tid", "")) for x in (links or []) if x.get("tid")}
                if link_tids:
                    matched = len(link_tids & set(mapping))
                    if matched / len(link_tids) < 0.5:
                        print(f"[!] 忽略过期板块映射：匹配率 {matched}/{len(link_tids)}")
                        return {tid: mapping[tid] for tid in direct_tids}
                return mapping
        except Exception as e:
            print(f"[!] 加载 {fname} 失败（忽略）: {e}", file=sys.stderr)
    print("[!] 未找到 threads_filtered/enriched.json，板块将完全依赖 LLM 从标题推断",
          file=sys.stderr)
    return mapping


def _detail_title(title: str) -> str:
    """去掉详情页标题中的论坛站点后缀，保留帖子原始标题。"""
    title = re.sub(r"\s*-\s*[^-\n]+\s*-\s*FLYERT\s*$", "", title or "", flags=re.I)
    return title.strip()


def restore_titles_from_details(links: list[dict], details: dict[str, dict]) -> int:
    """用详情页标题覆盖论坛列表页 CSS 截断的标题。"""
    restored = 0
    for link in links:
        detail = details.get(str(link.get("tid", "")))
        if not detail:
            continue
        title = _detail_title(detail.get("title", ""))
        if title and len(title) > len(link.get("title", "")):
            link["title"] = title
            restored += 1
    return restored


def call_llm(prompt: str, groups: list[dict], model_override: str | None,
             proxy: str | None = None, timeout: int = 180) -> str:
    """逐组调用：探测模型 → chat/completions，失败自动切下一组。

    返回 LLM 原始文本；全部失败返回 ""。
    指数退避重试策略：最多 5 次尝试，延迟 1s/2s/4s/8s。
    """
    import time
    proxies = proxy or DEFAULT_PROXY
    retry_delays = [1, 2, 4, 8]  # 秒数

    for gi, g in enumerate(groups, 1):
        key, base = g["key"], g["base"]
        models = [model_override] if model_override else probe_models(key, base, proxies)
        if not models:
            print(f"[-] 组{gi} {base} 未获取到可用模型，跳过该通道",
                  file=sys.stderr)
            continue
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
            for attempt in range(5):
                try:
                    with httpx.Client(trust_env=False, timeout=timeout, proxy=proxies) as client:
                        resp = client.post(url, headers={"Authorization": f"Bearer {key}"},
                                           json=payload)
                    if resp.status_code != 200:
                        print(f"[-] 组{gi} [{model}] HTTP {resp.status_code}: "
                              f"{resp.text[:200]} [{attempt+1}/5]", file=sys.stderr)
                        if attempt < 4:
                            delay = retry_delays[attempt]
                            print(f"  {delay}s 后重试...")
                            time.sleep(delay)
                            continue
                        break
                    data = resp.json()
                    raw = data["choices"][0]["message"]["content"] or ""
                    if not raw:
                        raw = data["choices"][0]["message"].get("reasoning_content", "")
                    return raw.strip()
                except httpx.TimeoutException:
                    print(f"[-] 组{gi} [{model}] 请求超时 ({timeout}s) [{attempt+1}/5]",
                          file=sys.stderr)
                    if attempt < 4:
                        delay = retry_delays[attempt]
                        print(f"  {delay}s 后重试...")
                        time.sleep(delay)
                        continue
                    break
                except Exception as e:
                    print(f"[-] 组{gi} [{model}] 调用异常: {e} [{attempt+1}/5]",
                          file=sys.stderr)
                    if attempt < 4:
                        delay = retry_delays[attempt]
                        print(f"  {delay}s 后重试...")
                        time.sleep(delay)
                        continue
                    break
    return ""


def strip_fences(raw: str) -> str:
    """去掉可能的 ```markdown ... ``` 围栏。"""
    m = re.search(r"```[a-zA-Z]*\s*\n(.*?)```", raw, re.DOTALL)
    return m.group(1).strip() if m else raw.strip()


# 标题明确表达求助/咨询时，优先级高于“积分/权益”等主题词。
QUESTION_TITLE_PATTERNS = (
    r"多久到账", r"什么时候到账", r"未到账", r"没到账", r"不到账",
    r"怎么", r"如何", r"是否", r"是不是", r"能否", r"可不可以",
    r"哪个", r"哪里", r"请教", r"咨询", r"求助", r"求问", r"帮我看看",
    r"为什么", r"为何", r"多久", r"怎么办", r"有必要", r"值得吗",
)
SECTION_ORDER = (
    "热门讨论", "新卡发行", "新卡发行&申卡下卡", "权益变更", "停发退市",
    "活动优惠", "公告通知", "疑问求助", "用卡经验", "其他",
)


def _section_name(header: str) -> str:
    """将 `## ⚠️ 权益变更` 归一化为可比较的栏目名称。"""
    name = re.sub(r"^##\s+", "", header).strip()
    return re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", name).strip()


def _post_title_from_block(block: list[str]) -> str:
    """从帖子块的链接行中提取标题，兼容冒号或空格分隔 URL。"""
    for line in block:
        m = re.match(r"^-\s*(?:🔗|📋)\s+(.+?)\s*(?:：|:)?\s*https?://", line.strip())
        if m:
            title = m.group(1).strip()
            if title.startswith("原帖 "):
                title = title[3:].strip()
            return title
    return ""


def _is_question_post(block: list[str]) -> bool:
    """判断帖子是否主要是求助/咨询，供分类后处理使用。"""
    title = _post_title_from_block(block)
    if not title:
        return False
    return any(re.search(pattern, title, re.IGNORECASE) for pattern in QUESTION_TITLE_PATTERNS)


def normalize_question_sections(md: str) -> str:
    """将标题明确为提问/求助的帖子统一移入「疑问求助」栏目。

    LLM 负责理解复杂语义，本规则只处理高置信度的标题句式，避免模型把
    “积分多久到账”一类问题误放进「权益变更」。热门榜单不参与移动。
    """
    lines = md.splitlines()
    section_starts = [i for i, line in enumerate(lines) if re.match(r"^##\s+", line)]
    if not section_starts:
        return md

    prefix = lines[:section_starts[0]]
    sections = []
    for pos, start in enumerate(section_starts):
        end = section_starts[pos + 1] if pos + 1 < len(section_starts) else len(lines)
        sections.append({"header": lines[start], "body": lines[start + 1:end]})

    moved: list[list[str]] = []
    for section in sections:
        if _section_name(section["header"]) in ("热门讨论", "疑问求助"):
            continue
        body = section["body"]
        post_starts = [i for i, line in enumerate(body) if re.match(r"^#{3,4}\s+", line)]
        if not post_starts:
            continue
        kept = body[:post_starts[0]]
        for pos, start in enumerate(post_starts):
            end = post_starts[pos + 1] if pos + 1 < len(post_starts) else len(body)
            block = body[start:end]
            if _is_question_post(block):
                moved.append(block)
            else:
                kept.extend(block)
        section["body"] = kept

    if not moved:
        return md

    target = next((s for s in sections if _section_name(s["header"]) == "疑问求助"), None)
    if target is None:
        target = {"header": "## 疑问求助", "body": []}
        # 按既有栏目顺序插入；找不到位置时追加到末尾。
        insert_at = len(sections)
        target_order = SECTION_ORDER.index("疑问求助")
        for i, section in enumerate(sections):
            name = _section_name(section["header"])
            if name in SECTION_ORDER and SECTION_ORDER.index(name) > target_order:
                insert_at = i
                break
        sections.insert(insert_at, target)

    while target["body"] and target["body"][-1] == "":
        target["body"].pop()
    if target["body"]:
        target["body"].append("")
    for block in moved:
        target["body"].extend(block)

    output = list(prefix)
    for section in sections:
        # 被全部移走的栏目不保留空栏目标题。
        if section["header"] != target["header"] and not any(
            re.match(r"^#{3,4}\s+", line) for line in section["body"]
        ):
            continue
        output.append(section["header"])
        output.extend(section["body"])
    return "\n".join(output).strip()


def backfill_stats(md: str, html_path: Path | None = None, detail_path: Path | None = None) -> str:
    """Replace or insert one canonical stats row per post, then fill the hot list."""
    tid_stats: dict[str, tuple[str, str]] = {}
    if detail_path and detail_path.exists():
        try:
            details = json.loads(detail_path.read_text(encoding="utf-8"))
            for item in details:
                tid = str(item.get("tid", ""))
                views = str(item.get("views", "?")).strip()
                replies = str(item.get("replies", "?")).strip()
                if tid:
                    tid_stats[tid] = (replies, views)
        except Exception:
            pass

    if not tid_stats and html_path and html_path.exists() and BeautifulSoup:
        try:
            html = html_path.read_text(encoding="utf-8-sig")
            soup = BeautifulSoup(html, "html.parser")
            for card in soup.find_all("div", style=lambda v: v and "position:relative;background:#f8fafc" in (v or "")):
                a = card.find("a", href=True)
                if not a:
                    continue
                tm = re.search(r"tid=(\d+)", a["href"])
                d = card.find("div", style=lambda v: v and "color:#94a3b8" in (v or ""))
                if tm and d:
                    sm = re.match(r"(\d+)\s*条回复\s*[·•]\s*(\d+)\s*次阅读", d.get_text(strip=True))
                    if sm:
                        tid_stats[tm.group(1)] = (sm.group(1), sm.group(2))
        except Exception:
            pass

    if not tid_stats:
        return md

    lines = md.splitlines()
    out = []
    skip_next = False
    for index, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        out.append(line)
        link_match = re.match(r"^-\s*(?:🔗|📋)\s+.*?(https?://\S+)", line)
        if not link_match:
            continue
        tm = re.search(r"tid=(\d+)", link_match.group(1))
        if not tm or tm.group(1) not in tid_stats:
            continue
        replies, views = tid_stats[tm.group(1)]
        stats_line = f"- 📊 {replies}回 / {views}阅"
        if index + 1 < len(lines) and re.match(r"^-\s*📊", lines[index + 1].strip()):
            out.append(stats_line)
            skip_next = True
        else:
            out.append(stats_line)
    md = "\n".join(out)
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


def _extract_title_from_link(ln: str) -> str:
    """从链接行 `- 🔗 标题：URL` 中提取标题，兼容 LLM 可能的格式变化。"""
    # 尝试匹配 `- 🔗 标题：URL` 的各种格式
    m = re.match(r"^-\s*(?:🔗|📋)\s+(.+?)\s+https?://", ln)
    if m:
        return m.group(1).strip()
    return ""


def _backfill_hot_list(md: str, title_stats: dict[str, tuple[str, str]]) -> str:
    """给热门讨论榜单行补 `（N回/N阅）`，仅当行内还没有回阅数。

    采用多策略匹配：
    1. 精确标题匹配（优先）
    2. 前缀匹配（标题可能被截断）
    3. 相似度匹配（解决标题变化问题）
    """
    if not title_stats:
        return md

    out = []
    for ln in md.splitlines():
        # 匹配榜单行：`1. **标题** [银行]` 或 `1. **标题**[银行]`
        tail_match = re.search(r"\s*(\[[^\]]*\])\s*$", ln)
        tail = tail_match.group(1) if tail_match else ""
        body = ln[:tail_match.start()].rstrip() if tail_match else ln
        m = re.match(r"^(\d+)[.、]\s*(?:\*\*(.+?)\*\*|(.+))$", body)
        if m:
            num = m.group(1)
            title = (m.group(2) or m.group(3)).strip()

            # 用「（N回/」判定是否已有回阅数
            if re.search(r"（[\d.]+K?M?回/", ln):
                out.append(ln)
                continue

            # 1. 精确匹配
            if title in title_stats:
                r, v = title_stats[title]
                ln = f"{num}. **{title}**（{r}回/{v}阅）{tail}".rstrip()
            # 2. 前缀匹配（标题被 LLM 截断或改写）
            else:
                found = False
                for stats_title, (r, v) in title_stats.items():
                    # 尝试匹配：title 是 stats_title 的前缀，或反过来
                    if title.startswith(stats_title[:20]) or stats_title.startswith(title[:20]):
                        ln = f"{num}. **{title}**（{r}回/{v}阅）{tail}".rstrip()
                        found = True
                        break

                # 3. 如果仍未找到，尝试特殊情况处理
                if not found and len(title) > 6:
                    # 特殊处理：有些标题可能只有前部分
                    for stats_title, (r, v) in title_stats.items():
                        # 如果 stats_title 包含 title 的关键词
                        if all(kw in stats_title for kw in title.split()[:3] if kw):
                            ln = f"{num}. **{title}**（{r}回/{v}阅）{tail}".rstrip()
                            found = True
                            break

        out.append(ln)
    return "\n".join(out)


def _ensure_hot_list(md: str, links: list[dict], details: dict[str, dict] | None = None) -> str:
    """Ensure the markdown contains a top-five hot list, even if the model omits it."""
    existing_hot = re.search(r"(?m)^##\s+.*热门讨论", md)
    if existing_hot:
        hot_end = re.search(r"(?m)^##\s+", md[existing_hot.end():])
        hot_body = md[existing_hot.end(): existing_hot.end() + hot_end.start() if hot_end else None]
        if re.search(r"(?m)^\s*\d+[.、]\s+", hot_body):
            return md

    details = details or {}
    rows = []
    for item in links:
        tid = str(item.get("tid", ""))
        detail = details.get(tid, {})
        raw_detail_title = str(detail.get("title", ""))
        clean_detail_title = re.sub(r"\s*-\s*[^-\n]+\s*-\s*FLYERT\s*$", "", raw_detail_title, flags=re.I).strip()
        title = clean_detail_title if len(clean_detail_title) > len(str(item.get("title", ""))) else str(item.get("title", "")).strip()
        if not title:
            continue
        try:
            replies = int(str(detail.get("replies", 0)).replace(",", ""))
        except (TypeError, ValueError):
            replies = 0
        try:
            views = int(str(detail.get("views", 0)).replace(",", ""))
        except (TypeError, ValueError):
            views = 0
        bank_match = re.search(r"-\s*([^-]+?)\s*-\s*FLYERT\s*$", raw_detail_title, flags=re.I)
        bank = bank_match.group(1).strip() if bank_match else "其他"
        rows.append((replies, views, title, bank, str(item.get("url", ""))))

    if not rows:
        return md
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    hot_lines = ["## 🔥 热门讨论"]
    for index, (replies, views, title, bank, url) in enumerate(rows[:5], 1):
        suffix = f" {url}" if url else ""
        hot_lines.append(f"{index}. **{title}**（{replies}回/{views}阅）[{bank}]{suffix}")

    lines = md.splitlines()
    if existing_hot:
        insert_at = md[:existing_hot.end()].count("\n") + 1
        return "\n".join(lines[:insert_at] + [""] + hot_lines[1:] + [""] + lines[insert_at:]).strip()
    first_section = next((i for i, line in enumerate(lines) if re.match(r"^##\s+", line)), None)
    if first_section is None:
        return md
    return "\n".join(lines[:first_section] + [""] + hot_lines + [""] + lines[first_section:]).strip()


def dedupe_detail_blocks(md: str) -> str:
    """按 tid 去重帖子详情块，避免热门/正文重复导致统计膨胀。"""
    lines = md.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < len(lines):
        if re.match(r"^#{3,4}\s+", lines[i]):
            j = i + 1
            while j < len(lines) and not re.match(r"^#{2,4}\s+", lines[j]):
                j += 1
            block = lines[i:j]
            tids = re.findall(r"tid=(\d+)", "\n".join(block))
            if tids and tids[0] in seen:
                i = j
                continue
            seen.update(tids)
            out.extend(block)
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip()


def move_hot_detail_cards(md: str) -> str:
    """热门区只保留榜单；误放在热门区的 ### 帖子移到其他板块。"""
    lines = md.splitlines()
    hot = next((i for i, line in enumerate(lines) if re.match(r"^##\s+.*热门讨论", line)), None)
    if hot is None:
        return md
    next_section = next((i for i in range(hot + 1, len(lines)) if re.match(r"^##\s+", lines[i])), len(lines))
    body = lines[hot + 1:next_section]
    starts = [i for i, line in enumerate(body) if re.match(r"^#{3,4}\s+", line)]
    if not starts:
        return md
    cards: list[str] = []
    kept = body[:starts[0]]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(body)
        cards.extend(body[start:end])
    prefix = lines[:hot + 1] + kept
    suffix = lines[next_section:]
    if not any(re.match(r"^##\s+.*其他", line) for line in suffix):
        suffix += ["", "## 其他"]
    suffix += [""] + cards
    return "\n".join(prefix + suffix).strip()
def clean_final_markdown(raw: str, links: list[dict], today_tids: set[str] | None = None) -> str:
    """Keep the final structured draft and discard model reasoning/revisions.

    严格按 today links 的 tid 集合过滤：LLM 可能从 threads_enriched/filtered.json
    幻觉补充旧帖，这些旧帖不在 today 的 links 里、也没有 detail 统计，
    会导致 HTML 渲染出「? 条回复」和概览条目数错误。
    today_tids 显式传入时优先使用（避免被 fallback 污染），否则从 links 推导。
    """
    headers = list(re.finditer(r"(?m)^#\s*飞客日报\s*📋?\s*\d{4}-\d{2}-\d{2}", raw))
    if headers:
        raw = raw[headers[-1].start():]
    if today_tids is None:
        today_tids = {str(item.get("tid", "")) for item in links if item.get("tid")}
    expected = today_tids
    lines = raw.splitlines()
    first_section = next((i for i, line in enumerate(lines) if re.match(r"^##\s+", line)), None)
    if first_section is None:
        return raw.strip()
    out = lines[:first_section]
    seen = set()
    note_seen = False
    finished = False
    # 当前 ### 帖子块是否保留：tid 不在 today links 里则整块丢弃（含标题）
    keep_block = True
    for line in lines[first_section:]:
        stripped = line.strip()
        if finished:
            break
        # 板块标题或帖子卡片标题：新块开始，默认保留
        if re.match(r"^##\s+", stripped) or re.match(r"^#{3,4}\s+", stripped):
            keep_block = True
            out.append(line)
            note_seen = False
            continue
        if re.match(r"^\d+(?:[.]|、)\s+", stripped) and not expected.intersection(seen):
            # 热门榜单项：若无 tid 且无「N回/N阅」数据，视为旧帖幻觉，剔除
            if not re.search(r"tid=\d+", stripped):
                if not re.search(r"\d+(?:\.\d+)?\s*[KMm]?\s*回\s*/\s*\d+", stripped):
                    continue
            out.append(line)
            continue
        tm = re.search(r"tid=(\d+)", line)
        if tm:
            tid = tm.group(1)
            seen.add(tid)
            # 严格过滤：tid 不在 today links 里，回溯剔除当前块（含 ### 标题）
            if expected and tid not in expected:
                block_start = len(out) - 1
                while block_start >= 0 and not re.match(r"^#{3,4}\s+", out[block_start]):
                    block_start -= 1
                if block_start >= 0:
                    out = out[:block_start]
                keep_block = False
                continue
            out.append(line)
            note_seen = False
            continue
        # 当前块被丢弃时，跳过其下的 📊/💬/正文 行
        if not keep_block:
            if not stripped:
                keep_block = True  # 空行后重置，等下一个标题块
            continue
        if re.match(r"^-\s*(?:📊|💬)", stripped):
            out.append(line)
            if "💬" in stripped:
                note_seen = True
            continue
        if not stripped:
            out.append(line)
            if expected and expected.issubset(seen) and note_seen:
                finished = True
            continue
        if expected and expected.issubset(seen) and note_seen:
            break
        if seen:
            out.append(line)
    return "\n".join(out).strip()

def make_subtitle(md: str) -> str:
    """Build a subtitle from the two highest-value items in the hot ranking."""
    hot = re.search(r"(?ms)^##\s+[^\n]*热门讨论[^\n]*\n(.*?)(?=^##\s+|\Z)", md)
    if not hot:
        return "今日日报"
    items = []
    for match in re.finditer(r"(?m)^\d+[.、]\s+(?:\*\*)?(.+?)(?:\*\*)?(?:（[^）]+）)?(?:\s+\[[^]]+\])?$", hot.group(1)):
        title = re.sub(r"\*\*", "", match.group(1)).strip(" ：:，。！？!? ")
        if title and title not in items:
            items.append(title[:18].rstrip("，。！？!? "))
        if len(items) == 2:
            break
    return "｜".join(items) if items else "今日日报"


def normalize_category_stats(md: str) -> str:
    """Rebuild the overview counts from rendered detail sections.

    散落在板块外的 ### 帖子（LLM 漏写 ## 板块标题时）归入「其他」，
    保证概览总数 = 真实 ### 帖子数。
    """
    lines = md.splitlines()
    counts = {}
    current = None
    for line in lines:
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            current = re.sub(r"^[^\u4e00-\u9fa5a-zA-Z]+", "", heading.group(1)).strip()
            continue
        if not re.match(r"^###\s+", line):
            continue
        # 热门讨论板块下的 ### 是详情卡片，也计入
        if current == "热门讨论":
            counts["其他"] = counts.get("其他", 0) + 1
        elif current:
            counts[current] = counts.get(current, 0) + 1
        else:
            counts["其他"] = counts.get("其他", 0) + 1
    total = sum(counts.values())
    if not total:
        overview = next((line for line in lines if re.match(r"^>\s*共\s*\d+\s*条讨论", line)), "")
        total_match = re.search(r"共\s*(\d+)\s*条讨论", overview)
        if not total_match:
            return md
        total = int(total_match.group(1))
        for name, value in re.findall(r"([^|/]+?)\s*(\d+)\s*条", overview):
            counts[name.strip()] = int(value)
    counted = sum(counts.values())
    # 以去重后的实际帖子块为准，避免热门榜重复项把概览总数抬高。
    if counted:
        total = counted
    order = ["新卡发行", "权益变更", "停发退市", "活动优惠", "公告通知", "疑问求助", "用卡经验", "其他"]
    stats = [f"{name} {counts[name]} 条" for name in order if counts.get(name)]
    replacement = f"> 共 {total} 条讨论 | {' / '.join(stats)} | 数据源：flyert.com.cn 信用卡版块"
    for i, line in enumerate(lines):
        if re.match(r"^>\s*共\s*\d+\s*条讨论", line):
            lines[i] = replacement
            break
    return "\n".join(lines)


# 论坛版块名 → 银行名的归一化映射。threads_filtered/enriched 的 category 是论坛
# 版块标签（如「招商银行」「求助问答」「见闻闲聊」），日报 ### 行首和热门榜
# [银行] 需要的是银行名。版块已是银行名时直接用；非银行版块不在此映射中，
# fix_bank_from_category 会跳过（保留 LLM 写的银行名或「其他」）。
SECTION_TO_BANK = {
    "工商银行": "工商银行", "建设银行": "建设银行", "招商银行": "招商银行",
    "交通银行": "交通银行", "农业银行": "农业银行", "中国银行": "中国银行",
    "中信银行": "中信银行", "浦发银行": "浦发银行", "民生银行": "民生银行",
    "兴业银行": "兴业银行", "光大银行": "光大银行", "平安银行": "平安银行",
    "华夏银行": "华夏银行", "邮储银行": "邮储银行", "广发银行": "广发银行",
    "汇丰银行": "汇丰银行", "花旗银行": "花旗银行", "渣打银行": "渣打银行",
    "东亚银行": "东亚银行", "恒生银行": "恒生银行",
}


def _bank_from_category(category: str) -> str | None:
    """把权威版块名归一化为日报银行名。非银行版块返回 None（不校正）。"""
    if not category:
        return None
    category = category.strip()
    if category in SECTION_TO_BANK:
        return SECTION_TO_BANK[category]
    # 版块名可能是「招行信用卡」「建行卡区」等带后缀的形式
    for sec, bank in SECTION_TO_BANK.items():
        if category.startswith(sec) or sec in category:
            return bank
    return None


def fix_bank_from_category(md: str, tid_category: dict[str, str]) -> str:
    """按 tid 用权威 category 覆盖 ### 行首和热门榜 [银行]，保留点评/摘要/分类。

    作用范围（均按 tid 匹配权威板块，仅在板块是银行名时才覆盖）：
    1. 帖子详情块 `### 银行名 摘要 [emoji?]` —— 替换行首银行名，保留摘要与尾部 emoji
    2. 热门讨论榜单 `N. **标题**（N回/N阅）[银行] URL` —— 替换 [银行]

    非银行版块（如「求助问答」「见闻闲聊」）不参与覆盖，避免把求助帖误改成银行名。
    """
    if not tid_category:
        return md

    # tid → 应写银行名（仅银行版块；非银行版块不校正）
    tid_bank: dict[str, str] = {}
    for tid, cat in tid_category.items():
        bank = _bank_from_category(cat)
        if bank:
            tid_bank[str(tid)] = bank
    if not tid_bank:
        return md

    lines = md.splitlines()
    out: list[str] = []
    pending_h3 = -1  # 待校正的 ### 行在 out 中的下标；-1 表示无

    for ln in lines:
        # 1. 帖子详情块：### 银行名 摘要 [emoji?]
        #    下一个非空 `- 🔗 ...：URL` 行含 tid，据此校正 ### 行首银行名。
        h3 = re.match(r"^(###)\s+(\S+)\s+(.*)$", ln)
        if h3:
            out.append(ln)
            pending_h3 = len(out) - 1
            continue

        # 2. 热门榜单行：N. **标题**（N回/N阅）[银行] URL
        hot = re.match(
            r"^(\d+)[.、]\s+(?:\*\*(.+?)\*\*|(.+?))"
            r"（\s*([\d.]+[KMm]?)\s*回\s*/\s*([\d.]+[KMm]?)\s*阅\s*）"
            r"\s*(\[[^\]]*\])?\s*(https?://\S*)?\s*$",
            ln,
        )
        if hot:
            num = hot.group(1)
            title = hot.group(2) or hot.group(3) or ""
            rep = hot.group(4)
            views = hot.group(5)
            url = hot.group(7) or ""
            tm = re.search(r"tid=(\d+)", url)
            if tm and tm.group(1) in tid_bank:
                bank = tid_bank[tm.group(1)]
                tail = f"[{bank}]"
            else:
                tail = hot.group(6) or ""
            suffix = f" {url}" if url else ""
            ln = f"{num}. **{title}**（{rep}回/{views}阅）{tail}{suffix}".rstrip()
            out.append(ln)
            continue

        # 3. - 🔗 标题：URL —— 若前面有 pending ### 行，按 tid 校正之
        link = re.match(r"^-\s*(?:🔗|📋)\s+.*?(https?://\S+)", ln)
        if link and pending_h3 >= 0:
            tm = re.search(r"tid=(\d+)", link.group(1))
            if tm and tm.group(1) in tid_bank:
                bank = tid_bank[tm.group(1)]
                old_h3 = out[pending_h3]
                # ### 银行名 摘要 [emoji?]
                m = re.match(r"^(###\s+)(\S+)(\s+.*)$", old_h3)
                if m:
                    out[pending_h3] = f"{m.group(1)}{bank}{m.group(3)}"
            pending_h3 = -1
            out.append(ln)
            continue

        # 任何非 🔗 行都意味着上个 ### 块已结束，清除 pending
        if pending_h3 >= 0 and ln.strip() and not re.match(r"^-\s*🔗", ln) and not re.match(r"^-\s*📊", ln):
            pending_h3 = -1
        out.append(ln)

    return "\n".join(out)


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

    # today links 的 tid 集合（严格过滤基准，不被 fallback 污染）
    today_tids = {str(it.get("tid", "")) for it in links if it.get("tid")}

    # 若链接不完整，尝试从 threads_enriched/filtered.json 补充完整数据
    if len(links) < 10:
        for fallback_file in ["threads_enriched.json", "threads_filtered.json"]:
            fallback_path = Path(fallback_file)
            if fallback_path.exists():
                try:
                    data = json.loads(fallback_path.read_text(encoding="utf-8"))
                    fallback_posts = data.get("posts", []) if isinstance(data, dict) else data
                    if fallback_posts and len(fallback_posts) > len(links):
                        # 补充缺失的链接
                        existing_tids = {l.get("tid") for l in links}
                        for post in fallback_posts:
                            if post.get("tid") not in existing_tids:
                                links.append({
                                    "title": post.get("title", ""),
                                    "url": post.get("url", ""),
                                    "tid": post.get("tid", "")
                                })
                        print(f"[+] 从 {fallback_file} 补充了 {len(fallback_posts) - len(existing_tids)} 条链接")
                        break
                except Exception as e:
                    pass

    ds = re.search(r"(\d{4})-(\d{2})-(\d{2})", links_path.name)
    ds = f"{datetime.now().year}-{ds.group(2)}-{ds.group(3)}" if ds else datetime.now().strftime("%Y-%m-%d")

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
                if it.get("tid") and (it.get("title") or it.get("content")):
                    details[str(it["tid"])] = it
        except Exception as e:
            print(f"[!] 详情加载失败（忽略）: {e}", file=sys.stderr)

    # 加载权威板块（tid → category），优先 threads_enriched.json，其次 threads_filtered.json
    tid_category = load_tid_category(links)

    # 交集检测：links 的 tid 与权威板块 tid 匹配率 < 50% 时警告，
    # 避免板块数据过期（残留旧 threads_filtered/enriched.json）时静默回退到 LLM 从标题推断。
    if tid_category and links:
        link_tids = {str(it.get("tid", "")) for it in links if it.get("tid")}
        matched = len(link_tids & set(tid_category.keys()))
        ratio = matched / len(link_tids) if link_tids else 0
        if ratio < 0.5:
            print(
                f"[!] 权威板块匹配率仅 {ratio:.0%}（{matched}/{len(link_tids)}），"
                f"threads_filtered/enriched.json 可能过期——板块校正将基本失效，"
                f"建议重新运行 fetcher.py 刷新 threads_filtered.json",
                file=sys.stderr,
            )
        else:
            print(f"[OK] 权威板块匹配率 {ratio:.0%}（{matched}/{len(link_tids)}）")

    if details:
        restored = restore_titles_from_details(links, details)
        if restored:
            print(f"[OK] 从详情页恢复 {restored} 条完整标题")
        print(f"[OK] 已加载 {len(details)} 条帖子详情作点评依据")
        prompt = build_prompt(links, ds, details, tid_category)
    else:
        print("[!] 未找到帖子详情，点评可能缺少原文依据（可先运行 fetch_threads_detail.py）",
              file=sys.stderr)
        prompt = build_prompt(links, ds, None, tid_category)

    if args.dry_run:
        print(prompt)
        return 0

    groups = load_llm_configs()
    proxy = None if (args.proxy or "").lower() == "none" else args.proxy
    raw = call_llm(prompt, groups, args.model, proxy=proxy)
    if not raw:
        print("[-] LLM 未返回内容（全部配置组失败）", file=sys.stderr)
        return 2
    md = clean_final_markdown(strip_fences(raw), links, today_tids)
    md = dedupe_detail_blocks(md)
    md = _ensure_hot_list(md, links, details)
    md = move_hot_detail_cards(md)

    # 对标题明确的求助/咨询做确定性校正，避免模型将“积分多久到账”归入权益变更。
    md = normalize_question_sections(md)
    md = normalize_category_stats(md)

    # 后处理强校正：按 tid 用权威板块覆盖 ### 行首和热门榜 [银行]，
    # 即便 LLM 把"经典白金卡"猜成交行也能被招商银行版块纠正。
    md = fix_bank_from_category(md, tid_category)

    # 格式自检：必须有日期标题、板块、🔗 链接
    if not re.search(r"^#\s*飞客日报\s*📋?\s*\d{4}-\d{2}-\d{2}", md):
        md = f"# 飞客日报 📋 {ds}\n\n{md}"
    if "## " not in md or "🔗" not in md:
        print("[-] LLM 输出缺少板块或链接，格式异常，前 500 字：", file=sys.stderr)
        print(md[:500], file=sys.stderr)
        return 2

    # 回填回复/阅读数（优先从详情 JSON，降级到 HTML）
    html_path = Path(args.html) if args.html else None
    md = backfill_stats(md, html_path, detail_path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mmdd = ds.replace("-", "")[4:]
    sub = make_subtitle(md)
    # Clean Windows-invalid filename chars: : | < > " / \ ? * (+ normalized punctuation)
    sub = sub.replace("：", "-").replace("｜", " ").replace("…", "")
    sub = re.sub(r'[:<>"/\\|?\*]', '', sub)  # Remove all Windows-illegal chars
    sub = sub.strip().rstrip(".")  # Remove trailing dots (Windows disallows)
    if not sub:  # Fallback if cleaning made it empty
        sub = "今日日报"
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
