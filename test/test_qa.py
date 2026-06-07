# -*- coding: utf-8 -*-
"""QA 集成测试 — run_qa() 跳过逻辑 + 报告生成（mock API）"""
import json, sys, os
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── run_qa() 跳过场景 ──────────────────────────────────────────────

class TestRunQaSkip:
    """配置缺失/无效时 run_qa() 应优雅跳过"""

    def test_no_config_file(self):
        """配置文件不存在 → 跳过"""
        from wechat_image_qa import run_qa
        ok, msg = run_qa(config_path=Path("/nonexistent/qa.json"))
        assert ok is True
        assert "跳过" in msg

    def test_bad_api_key_placeholder(self):
        """API key 为占位符 → 跳过"""
        from wechat_image_qa import run_qa
        cfg = {"provider": "qwen", "qwen_api_key": "YOUR_KEY_HERE", "model": "qwen-vl-max"}
        tmp = ROOT / "_test_qa_cfg.json"
        tmp.write_text(json.dumps(cfg), encoding="utf-8")
        try:
            ok, msg = run_qa(config_path=tmp)
            assert ok is True
            assert "跳过" in msg
            assert "API Key" in msg
        finally:
            tmp.unlink(missing_ok=True)

    def test_empty_api_key(self):
        """API key 为空 → 跳过"""
        from wechat_image_qa import run_qa
        cfg = {"provider": "qwen", "qwen_api_key": "", "model": "qwen-vl-max"}
        tmp = ROOT / "_test_qa_cfg.json"
        tmp.write_text(json.dumps(cfg), encoding="utf-8")
        try:
            ok, msg = run_qa(config_path=tmp)
            assert ok is True
            assert "跳过" in msg
        finally:
            tmp.unlink(missing_ok=True)

    def test_no_images_dir(self):
        """图片目录不存在 → 跳过"""
        from wechat_image_qa import run_qa
        ok, msg = run_qa(
            config_path=ROOT / "qa_config_qwen.json",
            image_dir=Path("/nonexistent/images"),
        )
        assert ok is True
        assert "跳过" in msg

    def test_empty_images_dir(self):
        """图片目录为空 → 跳过"""
        from wechat_image_qa import run_qa
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ok, msg = run_qa(
                config_path=ROOT / "qa_config_qwen.json",
                image_dir=Path(d),
            )
            assert ok is True
            assert "跳过" in msg

    def test_gemini_bad_key(self):
        """Gemini provider + 占位 key → 跳过"""
        from wechat_image_qa import run_qa
        cfg = {"provider": "gemini", "google_api_key": "YOUR_KEY_HERE", "model": "gemini-2.0-flash"}
        tmp = ROOT / "_test_qa_cfg.json"
        tmp.write_text(json.dumps(cfg), encoding="utf-8")
        try:
            ok, msg = run_qa(config_path=tmp)
            assert ok is True
            assert "跳过" in msg
        finally:
            tmp.unlink(missing_ok=True)


# ── run_qa() 正常流程（mock API） ──────────────────────────────────

class TestRunQaReport:
    """mock API 调用，验证报告生成逻辑"""

    def test_report_generated_with_mock_api(self, tmp_path):
        """mock API 返回正常内容 → 报告文件生成"""
        from wechat_image_qa import run_qa

        # 复制一张测试图片到临时目录
        cards_dir = ROOT / "_cards"
        test_images = list(cards_dir.glob("card_*.png"))
        if not test_images:
            import pytest
            pytest.skip("无现有卡片 PNG")

        tmp_img = tmp_path / test_images[0].name
        tmp_img.write_bytes(test_images[0].read_bytes())

        # mock 配置
        cfg = {
            "provider": "qwen",
            "qwen_api_key": "mock-key-not-real",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "output_dir": str(tmp_path),
        }
        cfg_path = tmp_path / "qa_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        # mock API 响应
        mock_response = """\
**设计类型**：信息图卡片
**图片数量**：1 张（图1 ~ 图1）
**问题总数**：A类 0 条 | B类 1 条 | C类 0 条 | D类 0 条 | E类 0 条 | F类 0 条 | 合计 1 条

---

### B 文字可读性（1 条）

**[可读-B01] 图1 — 标题字号偏小**
**问题**：主标题字号在 1080px 宽度下约 28px，低于建议值
**建议**：将字号从 28px 增大至 36px

---
"""
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_response))]
        )

        with patch("wechat_image_qa.create_qwen_client", return_value=mock_client):
            ok, msg = run_qa(config_path=cfg_path, image_dir=tmp_path)

        assert ok is True
        # 验证报告文件生成
        report_path = Path(msg)
        assert report_path.exists(), f"报告文件不存在: {msg}"
        content = report_path.read_text(encoding="utf-8")
        assert "公众号贴图验收报告" in content
        assert "文字可读性" in content

    def test_report_contains_date(self, tmp_path):
        """报告包含当天日期"""
        from wechat_image_qa import generate_report
        from datetime import datetime

        report = generate_report("测试 phase1", {}, [Path("test.png")])
        assert datetime.now().strftime("%Y-%m-%d") in report

    def test_extract_phase1_issues(self):
        """解析 Phase 1 报告中的问题分类"""
        from wechat_image_qa import extract_phase1_issues

        report = """\
### A 整体风格一致性（1 条）

**[风格-A01] 图1 vs 图2 — 色调不一致**
**问题**：主色调差异大
**建议**：统一配色

### B 文字可读性（2 条）

**[可读-B01] 图3 — 字号偏小**
**问题**：正文字号不足
**建议**：增大字号

**[可读-B02] 图1 — 对比度低**
**问题**：文字与背景对比不足
**建议**：加深文字颜色

### C 边界与溢出（0 条）

未发现问题
"""
        issues = extract_phase1_issues(report)
        assert "A" in issues
        assert "B" in issues
        assert "C" not in issues  # 0 条不收集
        assert "A01" in issues["A"]
        assert "B01" in issues["B"]
        assert "B02" in issues["B"]


# ── run_qa() 异常处理 ──────────────────────────────────────────────

class TestRunQaErrorHandling:
    """API 调用失败时的降级处理"""

    def test_api_exception_returns_ok(self, tmp_path):
        """API 抛异常 → 返回 ok=True + 错误信息（不中断主流程）"""
        from wechat_image_qa import run_qa

        # 放一张图片
        cards_dir = ROOT / "_cards"
        test_images = list(cards_dir.glob("card_*.png"))
        if not test_images:
            import pytest
            pytest.skip("无现有卡片 PNG")
        tmp_img = tmp_path / test_images[0].name
        tmp_img.write_bytes(test_images[0].read_bytes())

        cfg = {
            "provider": "qwen",
            "qwen_api_key": "real-key-but-will-fail",
            "model": "qwen-vl-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        }
        cfg_path = tmp_path / "qa_config.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        # mock 客户端创建成功但 API 调用失败
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("网络超时")

        with patch("wechat_image_qa.create_qwen_client", return_value=mock_client):
            ok, msg = run_qa(config_path=cfg_path, image_dir=tmp_path)

        assert ok is True  # 主流程不中断
        assert "跳过" in msg or "失败" in msg


# ── 主流程集成 ──────────────────────────────────────────────────────

class TestQaPipelineIntegration:
    """验证 QA 可被 run.py 的流程正确调用"""

    def test_import_run_qa(self):
        """run_qa 可从 wechat_image_qa 正常导入"""
        from wechat_image_qa import run_qa
        assert callable(run_qa)

    def test_run_qa_signature(self):
        """run_qa 签名包含 config_path 和 image_dir 参数"""
        import inspect
        from wechat_image_qa import run_qa
        sig = inspect.signature(run_qa)
        params = list(sig.parameters.keys())
        assert "config_path" in params
        assert "image_dir" in params

    def test_run_qa_return_type(self):
        """run_qa 返回 (bool, str) 元组"""
        from wechat_image_qa import run_qa
        result = run_qa(config_path=Path("/nonexistent"))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)
