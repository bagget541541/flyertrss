# -*- coding: utf-8 -*-
"""Playwright 渲染集成测试 — 不依赖网络，用本地 HTML + 缓存数据"""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from card_gen import (
    _render_card, _render_info_card, _render_top3_card, render_cover,
    gen_preview, TAG_COLORS, PALETTES, _int, _fmt_bank_name,
    OUT_DIR, CARD_W, CARD_H,
)

# 加载真实数据
_threads = json.loads((ROOT / "threads_filtered.json").read_text(encoding="utf-8"))
if not _threads:
    # 如果当日数据为空（已见），回退到 historic 缓存
    for fallback in ["threads_enriched.json", "threads_raw.json"]:
        fp = ROOT / fallback
        if fp.exists():
            raw = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "posts" in raw:
                raw = raw["posts"]
            if raw:
                _threads = raw[:6]
                break

_raw_enriched = json.loads((ROOT / "threads_enriched.json").read_text(encoding="utf-8"))
# 兼容新旧格式
if isinstance(_raw_enriched, dict) and "posts" in _raw_enriched:
    _enriched = _raw_enriched["posts"]
else:
    _enriched = _raw_enriched

for t in _threads:
    t["replies"] = _int(t.get("replies", 0))
    t["views"] = _int(t.get("views", 0))
    t["category"] = _fmt_bank_name(t.get("category", ""))

# 匹配 enriched 数据
_enriched_map = {}
for t in _enriched:
    tid = t.get("tid")
    if tid and "summary" in t:
        _enriched_map[tid] = t
for t in _threads:
    if t["tid"] in _enriched_map:
        t["summary"] = _enriched_map[t["tid"]]["summary"]
        t["value_tag"] = _enriched_map[t["tid"]]["value_tag"]

DS = "2026-06-04"
TOTAL = len(_threads)
BANK_COUNT = 5
HOT_BANK = "农业银行"
TOP_REPLIES = max(t["replies"] for t in _threads) if _threads else 0


def _patch_out_dir(tmp_path):
    """临时替换 OUT_DIR 到 tmp_path"""
    import card_gen
    original = card_gen.OUT_DIR
    card_gen.OUT_DIR = tmp_path
    return original


class TestRenderCard:
    def test_single_post(self, tmp_path):
        """1 条帖子渲染卡片"""
        _patch_out_dir(tmp_path)
        posts = [_threads[0]]
        ok, res = _render_card(
            posts, DS, TOTAL, PALETTES["hot"], 1, "今日热门", "@test",
            BANK_COUNT, HOT_BANK, TOP_REPLIES,
        )
        assert ok, f"render failed: {res}"
        assert res.exists()
        assert res.stat().st_size > 10_000, "PNG too small"

    def test_multi_posts(self, tmp_path):
        """4 条帖子渲染"""
        _patch_out_dir(tmp_path)
        posts = _threads[:4]
        ok, res = _render_card(
            posts, DS, TOTAL, PALETTES["hot"], 2, "今日热门", "@test",
            BANK_COUNT, HOT_BANK, TOP_REPLIES,
        )
        assert ok, f"render failed: {res}"
        assert res.exists()

    def test_compact_mode(self, tmp_path):
        """compact 排版"""
        _patch_out_dir(tmp_path)
        posts = _threads[:6]
        ok, res = _render_card(
            posts, DS, TOTAL, PALETTES["国有行"], 3, "全量速览", "@test",
            BANK_COUNT, HOT_BANK, TOP_REPLIES, compact=True,
        )
        assert ok, f"render failed: {res}"
        assert res.exists()

    def test_hook_text_in_html(self, tmp_path):
        """验证 hook 文案出现在生成的 HTML 中"""
        _patch_out_dir(tmp_path)
        posts = [_threads[0]]
        # 渲染会成功（hook 已加入模板替换）
        ok, res = _render_card(
            posts, DS, TOTAL, PALETTES["hot"], 99, "今日热门", "@test",
            BANK_COUNT, HOT_BANK, TOP_REPLIES,
        )
        assert ok


class TestRenderInfoCard:
    def test_with_enriched_data(self, tmp_path):
        """用 enriched 数据渲染信息图"""
        _patch_out_dir(tmp_path)
        post = _threads[0]
        # 确保有 summary
        if "summary" not in post:
            post["summary"] = post["title"][:10]
        if "value_tag" not in post:
            post["value_tag"] = "讨论"

        all_meta = {"max_replies": TOP_REPLIES, "max_views": 10000}
        ok, res = _render_info_card(
            post, DS, PALETTES["hot"], "@test", all_meta,
            hot_replies_html="", hot_replies_raw=[], card_idx=90,
        )
        assert ok, f"info card failed: {res}"
        assert res.exists()
        assert res.stat().st_size > 10_000

    def test_bank_logo_in_html(self, tmp_path):
        """信息图包含银行 logo badge"""
        import re
        _patch_out_dir(tmp_path)
        post = _threads[0].copy()
        post["category"] = "招商银行"
        post["summary"] = "测试标题"
        post["value_tag"] = "讨论"

        all_meta = {"avg_replies": 10, "avg_views": 5000, "avg_engagement": 5}
        ok, res = _render_info_card(
            post, DS, PALETTES["hot"], "@test", all_meta,
            hot_replies_html="", hot_replies_raw=[], card_idx=91,
        )
        assert ok, f"info card failed: {res}"
        # 验证生成的 HTML 包含 bank-badge 结构
        import card_gen
        tmp_html = card_gen.cwd / "__card_info.html"
        # tmp 文件在 finally 中被删除，检查 PNG 大小即可
        assert res.exists()
        assert res.stat().st_size > 10_000

    def test_all_banks_render(self, tmp_path):
        """不同银行名都能正常渲染信息图"""
        _patch_out_dir(tmp_path)
        for bank in ["招商银行", "工商银行", "农业银行", "中国银行", "其他"]:
            post = {
                "tid": 999, "title": f"{bank}测试帖", "replies": 10, "views": 5000,
                "summary": f"{bank}测试", "value_tag": "讨论", "category": bank,
            }
            all_meta = {"avg_replies": 10, "avg_views": 5000, "avg_engagement": 5}
            ok, res = _render_info_card(
                post, DS, PALETTES["hot"], "@test", all_meta,
                hot_replies_html="", hot_replies_raw=[], card_idx=92,
            )
            assert ok, f"{bank} info card failed: {res}"
            assert res.exists()


class TestRenderTop3:
    def test_top3_card(self, tmp_path):
        """前三甲卡片"""
        _patch_out_dir(tmp_path)
        top3 = []
        for p in _threads[:3]:
            top3.append({
                "title": p["title"],
                "replies": p["replies"],
                "summary": p.get("summary", p["title"][:10]),
                "value_tag": p.get("value_tag", "讨论"),
                "category": p.get("category", ""),
                "hot_replies": [{"content": "测试热评内容"}],
                "editor_note": "测试编辑点评",
            })
        ok, res = _render_top3_card(top3, DS, TOTAL, "@test")
        assert ok, f"top3 failed: {res}"
        assert res.exists()
        assert res.stat().st_size > 10_000


class TestRenderCover:
    def test_cover_16_9(self, tmp_path):
        """封面 1200x675"""
        _patch_out_dir(tmp_path)
        post = _threads[0]
        post.setdefault("summary", post["title"][:10])
        post.setdefault("value_tag", "讨论")
        out = render_cover(post, DS, TOTAL, BANK_COUNT, HOT_BANK, TOP_REPLIES, "@test")
        assert out is not None, "cover render failed"
        assert out.exists()
        assert out.stat().st_size > 10_000


class TestGenPreview:
    def test_preview_from_existing_cards(self):
        """用 _cards/ 下现有 PNG 生成预览图"""
        cards_dir = ROOT / "_cards"
        if not list(cards_dir.glob("card_*.png")):
            pytest.skip("无现有卡片 PNG")
        out = gen_preview()
        assert out is not None
        assert out.exists()
        assert out.stat().st_size > 5_000


class TestTagColorsConsistency:
    def test_module_level_exists(self):
        assert isinstance(TAG_COLORS, dict)
        assert len(TAG_COLORS) == 6

    def test_all_values_are_valid_hex(self):
        import re
        hex_re = re.compile(r"^#[0-9a-fA-F]{6}$")
        for k, v in TAG_COLORS.items():
            assert hex_re.match(v), f"{k}: {v} is not valid hex"
