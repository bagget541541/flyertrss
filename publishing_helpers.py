# -*- coding: utf-8 -*-
"""轻量发布辅助：供封面/公众号文章复用，不依赖 Playwright。"""
import math
from datetime import date

TAG_SCORE = {"限时": 30, "攻略": 25, "避坑": 20, "公告": 15, "实测": 10, "讨论": 0}
TITLE_BOOST_KW = {
    "新卡": 15, "申请": 12, "活动": 12, "炸裂": 12, "放水": 12, "大毛": 12,
    "权益": 10, "里程": 10, "积分": 10, "返现": 10, "免年费": 10,
    "缩水": 8, "调整": 8, "升级": 8, "TD": 10, "温暖": 8,
}


def parse_int(value):
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return 0


def format_bank_name(name):
    """缩短银行名: '中国农业银行' -> '农业银行', 保留'中国银行'"""
    if not name or name in ("其他", "求助问答"):
        return name
    stripped = name.replace("中国", "")
    if stripped == "银行":
        return name
    return stripped


BANK_PATTERNS = [
    ("中国工商银行", ["工商银行", "工行", "ICBC", "工银"]),
    ("中国农业银行", ["农业银行", "农行", "ABC"]),
    ("中国银行", ["中行", "BOC", "中国银行"]),
    ("中国建设银行", ["建设银行", "建行", "CCB"]),
    ("交通银行", ["交通银行", "交行"]),
    ("招商银行", ["招商银行", "招行", "CMB"]),
    ("浦发银行", ["浦发银行", "浦发"]),
    ("中信银行", ["中信银行", "中信", "CITIC"]),
    ("民生银行", ["民生银行", "民生", "CMBC"]),
    ("兴业银行", ["兴业银行", "兴业", "CIB"]),
    ("光大银行", ["光大银行", "光大", "CEB"]),
    ("平安银行", ["平安银行", "平安"]),
    ("华夏银行", ["华夏银行", "华夏"]),
    ("广发银行", ["广发银行", "广发", "CGB"]),
    ("邮储银行", ["邮储银行", "邮储", "邮政银行", "邮政"]),
    ("渤海银行", ["渤海银行", "渤海"]),
    ("浙商银行", ["浙商银行", "浙商"]),
    ("恒丰银行", ["恒丰银行", "恒丰"]),
    ("徽商银行", ["徽商银行", "徽商"]),
]


def detect_bank(title, content="", category="", replies_text=""):
    """从标题/内容/回帖/板块中检测银行名。优先级：标题 > 内容 > 板块"""
    def search(text):
        if not text:
            return None
        for bank, patterns in BANK_PATTERNS:
            for pattern in patterns:
                if pattern in text:
                    return bank
        return None

    bank = search(title)
    if bank:
        return bank
    bank = search(content) or search(replies_text)
    if bank:
        return bank
    bank = search(category)
    if bank:
        return bank
    return category or "其他"


def post_score(post):
    """综合评分：value_tag + 回复数(log) + 浏览量(log) + 标题关键词"""
    replies = parse_int(post.get("replies", 0))
    views = parse_int(post.get("views", 0))
    value_tag = post.get("value_tag", "讨论")
    title = post.get("title", "")

    tag_score = TAG_SCORE.get(value_tag, 0)
    reply_score = math.log1p(replies) * 5
    view_score = math.log1p(views) * 1.5
    title_score = sum(bonus for kw, bonus in TITLE_BOOST_KW.items() if kw in title)
    return tag_score + reply_score + view_score + title_score


def gen_editor_note(post):
    """根据帖子信息生成轻量编辑总结"""
    title = post.get("title", "")
    value_tag = post.get("value_tag", "讨论")
    reply_count = parse_int(post.get("replies", 0))
    today = date.today()
    month = today.month
    day = today.day

    notes = {
        "限时": (
            f"「{title[:20]}」有时效性，{reply_count} 条回复说明关注度高。窗口一过就没了，符合条件的今天就上车。",
            f"截止日期以官方公告为准，建议{month}月{day}日内完成操作。",
        ),
        "避坑": (
            f"「{title[:20]}」社区 {reply_count} 条讨论，踩坑反馈不少。别急着操作，先确认自身情况。",
            f"建议对照自身卡种和地区再决定，{month}月底前确认是否适用。",
        ),
        "攻略": (
            f"「{title[:20]}」操作路径清晰，{reply_count} 条回复已验证可行性。按步骤来就行。",
            "实操前截图保存步骤，本周内完成最佳。",
        ),
        "公告": (
            f"「{title[:20]}」银行政策调整，{reply_count} 条讨论说明影响面广。直接影响持卡权益，别等客服通知。",
            f"建议{month}月{day}日起对比调整前后差异，评估是否影响用卡计划。",
        ),
        "实测": (
            f"「{title[:20]}」真人实测数据，{reply_count} 条回复佐证。比官方宣传靠谱，但个体差异存在。",
            "参考其方法论而非具体数字，因地制宜。",
        ),
        "讨论": (
            f"「{title[:20]}」{reply_count} 条回复热度不低，说明这事确实纠结。核心看你的消费场景。",
            "别被极端观点带偏，结合自身需求做判断。",
        ),
    }
    summary, footnote = notes.get(value_tag, notes["讨论"])

    how_to_choose = ["怎么选", "如何选", "vs", "还是", "选择"]
    if any(kw in title for kw in how_to_choose):
        options = [
            value.strip()
            for value in title.replace("？", "").replace("?", "").replace("和", "|")
            .replace("还是", "|").replace("vs", "|").replace("VS", "|").split("|")
            if len(value.strip()) > 1
        ]
        if len(options) >= 2:
            summary = f"社区对该话题讨论激烈，双方各有拥趸。结合热评反馈，倾向选 {options[0]} 的偏多。"
            footnote = f"短期权益看 {options[0]}，长期持有成本看 {options[1]}。建议先算年费再决定。"

    return summary, footnote


def normalize_posts(posts):
    """补齐发布链路需要的标准字段，并按热度排序。"""
    normalized = []
    for post in posts:
        item = dict(post)
        item["replies"] = parse_int(item.get("replies", 0))
        item["views"] = parse_int(item.get("views", 0))
        raw_category = item.get("category", "")
        item["category"] = format_bank_name(detect_bank(item.get("title", ""), category=raw_category))
        if not item.get("summary"):
            item["summary"] = item.get("title", "")[:12]
        if not item.get("value_tag"):
            item["value_tag"] = "讨论"
        if not item.get("wechat_title"):
            item["wechat_title"] = item.get("summary") or item.get("title", "")[:20]
        normalized.append(item)
    normalized.sort(key=post_score, reverse=True)
    return normalized
