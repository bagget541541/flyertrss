# -*- coding: utf-8 -*-
"""LLM 富化 — 为帖子生成摘要、公众号标题、价值标签 + 文章级元数据"""
import json, os, sys, httpx, re
from pathlib import Path
from datetime import date

import settings

cwd = settings.CWD
os.chdir(str(cwd))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

K = settings.LLM_KEY
B = settings.LLM_BASE
M = settings.LLM_MODEL

# ── 价值标签映射 ──
TAG_MAP = {"xianshi": "限时", "bikeng": "避坑", "gonglue": "攻略",
           "gonggao": "公告", "taolun": "讨论", "shiice": "实测"}
TAG_RANK = ["限时", "避坑", "攻略", "公告", "实测", "讨论"]

# ── 系统 Prompt ──
SYSTEM_PROMPT = (
    "You are a credit card content editor. For each post, return a JSON array with EXACTLY these fields:\n"
    "- summary: Chinese 10-char summary of the post\n"
    "- wechat_title: Catchy WeChat article title, ≤22 Chinese chars, include numbers, action-oriented, MUST NOT be empty\n"
    "- value_tag: one of xianshi/bikeng/gonglue/gonggao/taolun/shiice\n"
    "Return ONLY the JSON array, no markdown, no explanation."
)

EXAMPLE_JSON = '[{"summary":"农行里程缩水","wechat_title":"农行里程比例调整！速换","value_tag":"xianshi"},{"summary":"经典白清退","wechat_title":"招行经典白终于清退","value_tag":"gonglue"}]'


def load_data(path=None):
    """读取 threads_filtered.json"""
    p = path or settings.FILTERED_PATH
    if not p.exists():
        print(f"[-] {p} 不存在")
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def build_prompt(posts):
    """构建 LLM 用户 prompt"""
    lines = "\n".join(f'{i+1}. {t["title"]}' for i, t in enumerate(posts))
    return lines + "\n\nExample JSON:\n" + EXAMPLE_JSON


def call_llm(posts, api_key=None, api_base=None, model=None):
    """调用 LLM 批量富化帖子，返回解析后的 JSON 数组"""
    key = api_key or K
    base = api_base or B
    mdl = model or M
    if not key or not base:
        print("[-] LLM 未配置，跳过 LLM 富化")
        return []

    url = f"{base.rstrip('/')}/chat/completions"
    prompt = build_prompt(posts)
    payload = {
        "model": mdl,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 8192,
    }

    print(f"LLM... ({len(posts)} posts)")
    for attempt in range(2):
        try:
            with httpx.Client(trust_env=False, timeout=120) as client:
                resp = client.post(url, headers={"Authorization": f"Bearer {key}"},
                                   json=payload)
            if resp.status_code != 200:
                print(f"[-] LLM API 返回 {resp.status_code}: {resp.text[:300]}")
                if attempt == 0:
                    print("  重试...")
                    continue
                return []
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            if not raw:
                raw = data["choices"][0]["message"].get("reasoning_content", "")
            return parse_llm_response(raw)
        except httpx.TimeoutException:
            print(f"[-] LLM 请求超时 (120s) [{attempt+1}/2]")
            if attempt == 0:
                print("  重试...")
                continue
            return []
        except Exception as e:
            print(f"[-] LLM 调用异常: {e}")
            if attempt == 0:
                print("  重试...")
                continue
            return []
    return []


def parse_llm_response(raw):
    """从 LLM 回复中提取 JSON 数组"""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        print("err:", raw[:300])
        return []
    enriched = json.loads(m.group())
    if isinstance(enriched, dict):
        enriched = list(enriched.values())
    print(f"parsed: {len(enriched)}")
    return enriched


def _make_wechat_fallback(title, summary):
    """从标题+摘要生成公众号标题 fallback"""
    t = title.strip()
    if len(t) <= 18:
        return t
    for c in "的·—–：:：":
        idx = t.find(c)
        if 6 < idx < 18:
            return t[:idx+1] + "..."
    return t[:18] + "…"


def enrich_posts(posts, llm_results):
    """将 LLM 结果合并到帖子数据中，含 fallback"""
    for i, t in enumerate(posts):
        if i < len(llm_results) and isinstance(llm_results[i], dict):
            rt = llm_results[i].get("value_tag", "").lower()
            t["summary"] = llm_results[i].get("summary", t["title"][:12])
            t["value_tag"] = TAG_MAP.get(rt, "讨论")
            wt = llm_results[i].get("wechat_title", "")
            t["wechat_title"] = wt if wt else _make_wechat_fallback(t["title"], t["summary"])
        else:
            t["summary"] = t["title"][:12]
            t["value_tag"] = "讨论"
            t["wechat_title"] = _make_wechat_fallback(t["title"], t["summary"])
    return posts


def generate_article_meta(posts, edition="晚报"):
    """生成文章级元数据（标题/摘要/统计）"""
    if not posts:
        return {"article_title": "", "article_desc": "", "edition": edition,
                "date": date.today().isoformat(), "total_posts": 0,
                "bank_count": 0, "hot_bank": "", "top_replies": "0", "top_tag": ""}

    hot_tags = [t.get("value_tag", "") for t in posts if t.get("value_tag", "") in TAG_RANK[:3]]
    hot_tag = hot_tags[0] if hot_tags else "讨论"
    top_post = posts[0]
    top_wt = top_post.get("wechat_title", "") or top_post.get("summary", "")
    top_replies = top_post.get("replies", "0")
    bank_names = list(set(t.get("category", "") for t in posts if t.get("category", "")))
    bank_count = len(bank_names)
    hot_bank = bank_names[0] if bank_names else ""
    today = date.today().isoformat()

    article_title = f"飞客{edition} | {top_wt}"
    if len(article_title) > 30:
        article_title = f"飞客{edition} | {top_post.get('summary', '今日信用卡情报')}"

    article_desc = f"今日{bank_count}家银行{len(posts)}条讨论"
    if top_replies:
        article_desc += f"，最热帖{top_replies}条回复"
    if hot_tag in ("限时", "避坑"):
        article_desc += f"，含{hot_tag}提醒"

    return {
        "article_title": article_title,
        "article_desc": article_desc,
        "edition": edition,
        "date": today,
        "total_posts": len(posts),
        "bank_count": bank_count,
        "hot_bank": hot_bank,
        "top_replies": top_replies,
        "top_tag": hot_tag,
    }


def save_output(posts, article_meta, path=None):
    """保存富化结果到 threads_enriched.json"""
    out = {"posts": posts, "article": article_meta}
    p = path or settings.ENRICHED_PATH
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {len(posts)} posts, article_title={article_meta.get('article_title', '')}")
    print(f"       article_desc={article_meta.get('article_desc', '')}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM 富化帖子")
    parser.add_argument("--edition", choices=["早报", "晚报"], default=None,
                        help="版次，默认按时间自动判断")
    args = parser.parse_args()

    edition = args.edition
    if edition is None:
        h = date.today().strftime("%H")
        edition = "早报" if int(h) < 12 else "晚报"

    posts = load_data()
    if not posts:
        print("无数据")
        return

    llm_results = call_llm(posts)
    posts = enrich_posts(posts, llm_results)

    article_meta = generate_article_meta(posts, edition=edition)
    save_output(posts, article_meta)


if __name__ == "__main__":
    main()
