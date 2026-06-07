# -*- coding: utf-8 -*-
"""纯逻辑单元测试 — 不依赖网络、Playwright、LLM"""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── card_gen.py 纯函数 ──────────────────────────────────────────────

from card_gen import _smart_truncate, _int, _fmt_bank_name, _detect_bank, _ds_meta, _gen_editor_note, TAG_COLORS, BANK_LOGO_MAP, _get_bank_logo, BANK_ASSETS_DIR


class TestSmartTruncate:
    def test_short_text_passthrough(self):
        assert _smart_truncate("短文本", 150) == "短文本"

    def test_exact_boundary(self):
        text = "a" * 150
        assert _smart_truncate(text, 150) == text

    def test_truncate_at_period(self):
        text = "前半段内容很重要。后半段内容也很重要，需要被截断掉"
        result = _smart_truncate(text, 15)
        assert result.endswith("。")
        assert len(result) <= 16  # 含句号

    def test_truncate_at_exclaim(self):
        text = "重要通知！请大家注意"
        result = _smart_truncate(text, 10)
        assert "！" in result

    def test_truncate_at_question(self):
        text = "怎么办呢？求帮助"
        result = _smart_truncate(text, 8)
        assert "？" in result

    def test_no_sentence_boundary_adds_ellipsis(self):
        text = "这是一段没有标点符号的很长很长的文本用来测试智能截断功能"
        result = _smart_truncate(text, 15)
        assert result.endswith("…")
        assert len(result) == 16  # 15 chars + ellipsis

    def test_truncate_prefers_later_boundary(self):
        text = "短。这是一段较长的内容应该在第二个句号处截断才对。这是第三段多余部分在这里"
        result = _smart_truncate(text, 35)
        assert result.endswith("。")
        assert "截断才对" in result


class TestInt:
    def test_normal_int(self):
        assert _int(42) == 42

    def test_string_number(self):
        assert _int("100") == 100

    def test_empty_string(self):
        assert _int("") == 0

    def test_none(self):
        assert _int(None) == 0

    def test_non_numeric(self):
        assert _int("abc") == 0

    def test_float_string(self):
        assert _int("3.14") == 0


class TestFmtBankName:
    def test_removes_china_prefix(self):
        assert _fmt_bank_name("中国农业银行") == "农业银行"

    def test_no_china_prefix(self):
        assert _fmt_bank_name("招商银行") == "招商银行"

    def test_china_in_middle(self):
        assert _fmt_bank_name("中国银行") == "中国银行"

    def test_empty(self):
        assert _fmt_bank_name("") == ""



class TestDetectBank:
    def test_title_keyword(self):
        assert _detect_bank("工行放水了", category="其他") == "中国工商银行"

    def test_title_abbrev(self):
        assert _detect_bank("招行经典白清退", category="招商银行") == "招商银行"

    def test_no_title_fallback_category(self):
        assert _detect_bank("15554878月底有没有尊享积分过期的朋友", category="中国银行") == "中国银行"

    def test_content_detection(self):
        assert _detect_bank("月底有没有积分过期", content="我是中国银行的持卡人", category="求助问答") == "中国银行"

    def test_empty_all(self):
        assert _detect_bank("", category="") == "其他"

    def test_boc_in_title(self):
        assert _detect_bank("中行信用卡活动", category="其他") == "中国银行"

class TestDsMeta:
    def test_normal_date(self):
        vol, cn_date, tagline = _ds_meta("2026-06-04")
        assert vol == "VOL.2026.06.04"
        assert "6月4日" in cn_date
        assert "星期四" in cn_date

    def test_january(self):
        vol, cn_date, _ = _ds_meta("2026-01-01")
        assert vol == "VOL.2026.01.01"
        assert "1月1日" in cn_date

    def test_weekday_accuracy(self):
        # 2026-06-01 is Monday
        _, cn_date, _ = _ds_meta("2026-06-01")
        assert "星期一" in cn_date


class TestGenEditorNote:
    def test_each_value_tag_produces_output(self):
        for vt in ["限时", "避坑", "攻略", "公告", "实测", "讨论"]:
            post = {"title": "测试帖子标题内容", "value_tag": vt, "category": "测试银行"}
            summary, footnote = _gen_editor_note(post)
            assert summary, f"value_tag={vt} returned empty summary"
            assert footnote, f"value_tag={vt} returned empty footnote"

    def test_how_to_choose_extracts_options(self):
        post = {"title": "招行钻石卡还是浦发超白金？怎么选", "value_tag": "讨论", "category": "招商银行"}
        summary, footnote = _gen_editor_note(post)
        # 应该触发选项提取分支
        assert "招行" in summary or "招行钻石卡" in summary or len(summary) > 10

    def test_how_to_choose_vs(self):
        post = {"title": "中信i白 vs 民生精英白 vs 广发臻享白", "value_tag": "讨论", "category": "中信银行"}
        summary, footnote = _gen_editor_note(post)
        assert summary  # 至少有内容

    def test_long_title_truncation_in_template(self):
        long_title = "这是一个非常非常长的帖子标题用来测试模板中的标题截断逻辑是否正常工作"
        post = {"title": long_title, "value_tag": "攻略", "category": "测试"}
        summary, _ = _gen_editor_note(post)
        assert long_title[:20] in summary


# ── TAG_COLORS 模块级常量 ───────────────────────────────────────────

class TestTagColors:
    def test_exists_and_has_all_keys(self):
        expected = {"限时", "避坑", "攻略", "公告", "讨论", "实测"}
        assert set(TAG_COLORS.keys()) == expected

    def test_values_are_hex_colors(self):
        for k, v in TAG_COLORS.items():
            assert v.startswith("#"), f"{k} color {v} is not hex"
            assert len(v) == 7, f"{k} color {v} is not 7-char hex"


# ── fetcher.py 纯函数 ───────────────────────────────────────────────

import importlib
sys.path.insert(0, str(ROOT))
import fetcher as f_mod


class TestIsWaf:
    def test_normal_html(self):
        assert f_mod._is_waf("<html><body>OK</body></html>") is False

    def test_403_forbidden(self):
        html = "403 Forbidden\nAccess Denied" + "x" * 200
        assert f_mod._is_waf(html) is True

    def test_empty_string(self):
        assert f_mod._is_waf("") is False

    def test_403_only_no_denied(self):
        # 只有 403 Forbidden 但没有 Access Denied → 不算 WAF
        assert f_mod._is_waf("403 Forbidden\nSome other error page content") is False


class TestDetectTotalPages:
    def test_single_page(self):
        html = "<div>1</div>"
        assert f_mod.detect_total_pages(html) == 1

    def test_no_footer(self):
        assert f_mod.detect_total_pages("no footer here") == 1

    def test_empty_string(self):
        assert f_mod.detect_total_pages("") == 1


class TestBuildPageUrl:
    def test_page_1(self):
        url = f_mod.build_page_url(1)
        assert "forum-creditcard-1.html" in url
        assert f_mod.BASE_URL in url

    def test_page_2(self):
        url = f_mod.build_page_url(2)
        assert "page=2" in url
        assert f_mod.BASE_URL in url


class TestIsNoise:
    def test_normal_post_kept(self):
        t = {"title": "正常帖子标题内容测试", "replies": 10, "views": 5000}
        assert f_mod.is_noise(t) is None

    def test_ad_low_engagement_filtered(self):
        t = {"title": "收中介费代办理", "replies": 2, "views": 100}
        result = f_mod.is_noise(t)
        assert result is not None
        assert "ad" in result

    def test_ad_high_engagement_kept(self):
        t = {"title": "收中介费代办理", "replies": 15, "views": 8000}
        assert f_mod.is_noise(t) is None

    def test_too_short(self):
        t = {"title": "短", "replies": 10, "views": 5000}
        result = f_mod.is_noise(t)
        assert result == "too short"

    def test_low_engagement(self):
        t = {"title": "正常标题长度够了", "replies": 1, "views": 100}
        result = f_mod.is_noise(t)
        assert result == "low engagement"

    def test_boundary_replies(self):
        t = {"title": "正常标题长度够了", "replies": 3, "views": 100}
        assert f_mod.is_noise(t) is None  # replies >= MIN_REP


# ── 集成：filter_threads + load_seen + save_seen ─────────────────────

class TestFilterIntegration:
    def test_filter_threads_with_seen(self, sample_threads):
        kept, dropped = f_mod.filter_threads(sample_threads[:5])
        # 至少有部分结果
        assert isinstance(kept, list)
        assert isinstance(dropped, list)

    def test_save_seen_roundtrip(self, tmp_path):
        tids = {"123", "456", "789"}
        p = str(tmp_path / "seen.json")
        f_mod.save_seen(tids, p)
        loaded = f_mod.load_seen(p)
        assert loaded == {"123", "456", "789"}

    def test_load_seen_existing(self):
        seen = f_mod.load_seen(str(ROOT / "seen_tids.json"))
        assert isinstance(seen, set)
        assert len(seen) > 0


# ── 编辑点评回写逻辑 ─────────────────────────────────────────────────

class TestEditorNoteBackfill:
    """测试 card_gen.py main() 中缺失 editor_note 的补生成逻辑"""

    def _backfill(self, enriched_posts, mock_opinion):
        """模拟 card_gen.py 中的回写循环，直接用 mock 替换"""
        for ep in enriched_posts:
            if ep.get("editor_note"):
                continue
            note, action = mock_opinion(ep, "", "")
            ep["editor_note"] = note + (" → " + action if action else "")

    def test_missing_notes_get_filled(self):
        posts = [
            {"tid": 1, "title": "帖子A"},
            {"tid": 2, "title": "帖子B"},
            {"tid": 3, "title": "帖子C"},
        ]
        call_count = [0]
        def fake_opinion(post, *args, **kwargs):
            call_count[0] += 1
            return f"点评{post['tid']}", "建议操作"

        self._backfill(posts, fake_opinion)
        assert call_count[0] == 3
        for p in posts:
            assert p["editor_note"], f"tid={p['tid']} 缺失 editor_note"

    def test_existing_notes_preserved(self):
        posts = [
            {"tid": 1, "title": "帖子A", "editor_note": "已有点评A"},
            {"tid": 2, "title": "帖子B"},
            {"tid": 3, "title": "帖子C", "editor_note": "已有点评C"},
        ]
        call_count = [0]
        def fake_opinion(post, *args, **kwargs):
            call_count[0] += 1
            return f"新点评{post['tid']}", ""

        self._backfill(posts, fake_opinion)
        # 只有 tid=2 应该被调用
        assert call_count[0] == 1
        assert posts[0]["editor_note"] == "已有点评A"
        assert posts[2]["editor_note"] == "已有点评C"
        assert "新点评2" in posts[1]["editor_note"]

    def test_action_appended_with_arrow(self):
        posts = [{"tid": 1, "title": "测试帖"}]
        def fake_opinion(post, *args, **kwargs):
            return "观点内容", "行动建议"

        self._backfill(posts, fake_opinion)
        assert posts[0]["editor_note"] == "观点内容 → 行动建议"

    def test_no_action_omits_arrow(self):
        posts = [{"tid": 1, "title": "测试帖"}]
        def fake_opinion(post, *args, **kwargs):
            return "观点内容", ""

        self._backfill(posts, fake_opinion)
        assert posts[0]["editor_note"] == "观点内容"

    def test_mixed_scenario(self):
        """模拟真实场景：top3 已有 + 其余缺失"""
        posts = [
            {"tid": 1, "title": "Top1", "editor_note": "LLM精选点评1"},
            {"tid": 2, "title": "Top2", "editor_note": "LLM精选点评2"},
            {"tid": 3, "title": "Top3", "editor_note": "LLM精选点评3"},
            {"tid": 4, "title": "普通帖4"},
            {"tid": 5, "title": "普通帖5"},
            {"tid": 6, "title": "普通帖6"},
            {"tid": 7, "title": "普通帖7"},
        ]
        call_count = [0]
        def fake_opinion(post, *args, **kwargs):
            call_count[0] += 1
            return f"补生成{post['tid']}", "建议"

        self._backfill(posts, fake_opinion)
        assert call_count[0] == 4  # 只补4条
        for p in posts:
            assert p["editor_note"], f"tid={p['tid']} 缺失 editor_note"
        # top3 没被覆盖
        assert posts[0]["editor_note"] == "LLM精选点评1"
        assert posts[1]["editor_note"] == "LLM精选点评2"
        assert posts[2]["editor_note"] == "LLM精选点评3"


# ── 银行 logo 系统 ─────────────────────────────────────────────────

class TestBankLogoMap:
    """BANK_LOGO_MAP 映射完整性"""

    def test_all_mapped_banks_have_svg_files(self):
        """每个映射的银行都有对应 SVG 文件"""
        for bank_name, svg_key in BANK_LOGO_MAP.items():
            svg_path = BANK_ASSETS_DIR / f"{svg_key}.svg"
            assert svg_path.exists(), f"{bank_name} -> {svg_key}.svg 不存在"

    def test_default_svg_exists(self):
        """default.svg 兜底文件存在"""
        assert (BANK_ASSETS_DIR / "default.svg").exists()

    def test_map_covers_all_bank_patterns(self):
        """BANK_LOGO_MAP 覆盖所有 BANK_PATTERNS 中的银行"""
        from card_gen import BANK_PATTERNS
        for full_name, _ in BANK_PATTERNS:
            short = _fmt_bank_name(full_name)
            assert short in BANK_LOGO_MAP, f"BANK_PATTERNS 中的 {full_name}（{short}）未在 BANK_LOGO_MAP 中"

    def test_svg_files_are_valid(self):
        """所有 SVG 文件内容以 <svg 开头"""
        for svg_file in BANK_ASSETS_DIR.glob("*.svg"):
            content = svg_file.read_text(encoding="utf-8").strip()
            assert content.startswith("<svg"), f"{svg_file.name} 不是有效 SVG"


class TestGetBankLogo:
    """_get_bank_logo 路径解析"""

    def test_known_bank_returns_correct_path(self):
        """已知银行返回对应 SVG 路径"""
        path = _get_bank_logo("招商银行")
        assert "cmb.svg" in path
        assert path.endswith(".svg")

    def test_unknown_bank_returns_default(self):
        """未知银行返回 default.svg"""
        path = _get_bank_logo("不存在的银行")
        assert "default.svg" in path

    def test_empty_name_returns_default(self):
        """空名称返回 default.svg"""
        path = _get_bank_logo("")
        assert "default.svg" in path

    def test_other_fallback(self):
        """'其他' 返回 default.svg"""
        path = _get_bank_logo("其他")
        assert "default.svg" in path

    def test_all_banks_return_existing_files(self):
        """所有 BANK_PATTERNS 中的银行都返回存在的文件"""
        from card_gen import BANK_PATTERNS
        for full_name, _ in BANK_PATTERNS:
            short = _fmt_bank_name(full_name)
            path = Path(_get_bank_logo(short))
            assert path.exists(), f"{short} 的 logo 文件不存在: {path}"

    def test_path_is_posix_format(self):
        """返回路径使用正斜杠（POSIX 格式）"""
        path = _get_bank_logo("工商银行")
        assert "\\" not in path, f"路径包含反斜杠: {path}"
