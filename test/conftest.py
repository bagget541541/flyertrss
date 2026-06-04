# -*- coding: utf-8 -*-
"""共享 fixtures — sample 数据、临时路径、工作目录"""
import json, os, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _chdir():
    """确保 CWD 在项目根目录（card_gen.py 用 __file__ 定位模板）"""
    os.chdir(str(ROOT))
    yield
    os.chdir(str(ROOT))


@pytest.fixture
def sample_threads():
    """threads_filtered.json 的真实数据（16 条）"""
    p = ROOT / "threads_filtered.json"
    if not p.exists():
        pytest.skip("threads_filtered.json 不存在")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def sample_enriched():
    """threads_enriched.json 的真实数据（22 条，含 summary + value_tag）"""
    p = ROOT / "threads_enriched.json"
    if not p.exists():
        pytest.skip("threads_enriched.json 不存在")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def tmp_out(tmp_path):
    """临时输出目录"""
    d = tmp_out = tmp_path / "cards"
    d.mkdir()
    return d
