#!/usr/bin/env python3
"""公众号贴图验收工具 — wechat-image-qa-reviewer 单模块实现

用法:
    python wechat_image_qa.py                          # 默认用 qa_config.json
    python wechat_image_qa.py --config qa_config_qwen.json  # 指定配置文件
    python wechat_image_qa.py _cards/card_01.png _cards/card_02.png ...  # 指定图片
"""

import sys
import json
import os
import base64
import argparse
from datetime import datetime
from pathlib import Path

from PIL import Image

# ── 配置 ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG = SCRIPT_DIR / "qa_config.json"

def load_config(config_path):
    if not config_path.exists():
        sys.exit(f"找不到配置文件 {config_path}")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    provider = cfg.get("provider", "gemini")
    if provider == "gemini":
        if cfg.get("google_api_key", "").startswith("YOUR_"):
            sys.exit("请先在配置文件中填入真实的 Google API Key")
    elif provider == "qwen":
        if cfg.get("qwen_api_key", "").startswith("YOUR_"):
            sys.exit("请先在配置文件中填入真实的 DashScope API Key")
    return cfg

# ── Prompt ────────────────────────────────────────────────────────────

PHASE1_PROMPT = """\
你是一名专业的公众号视觉设计质检员。请对输入的一组公众号推文配图做全面视觉质量检查。

## 你的任务

### 第一步：建立整体印象
通览所有图片后，输出：
- 设计类型（如"深色系信息图卡片"）
- 目标受众和阅读场景
- 图片总数量及编号（按顺序标记为图1、图2……）

### 第二步：六类检查

#### A 整体风格一致性（多图时检查，单图跳过）
- 主色调是否统一，有无突兀跳色
- 字体体系是否跨图一致
- 圆角/边框风格是否统一
- 间距体系是否视觉相当
- 装饰元素语言是否同源
- 版式方向是否一致

#### B 文字可读性
- 最小字号是否过小（1080px宽时正文≥28px，标题≥40px）
- 文字与背景对比度是否足够
- 渐变/图案背景叠字是否有蒙层保障
- 文字是否压图导致识别困难
- 行距字间距是否合理
- 文字是否被截断或溢出

#### C 边界与溢出
- 内容是否被图片边缘截断
- 四边安全边距是否≥3%（约32px@1080px）
- 前景是否意外遮挡关键内容
- 拼接图是否有白缝或错位

#### D 紧凑度与呼吸感
- 是否过度紧凑（段落间距<字号0.5倍、模块无分隔堆叠）
- 是否大片空白（某区域留白>25%且无意图）
- 空白分布是否不均（上下/左右失衡）
- 局部元素是否黏连无间距

#### E 元素堆叠与层次
- 是否有无意义元素堆叠形成视觉噪音
- 主次层次是否模糊（标题/正文权重相近）
- 图标与文字排列是否混乱
- 同主题内容是否视觉归组
- 装饰是否喧宾夺主

#### F 图文配合
- 配图内容与文字是否相关
- 图片是否模糊或像素低
- 人物/主体是否被截断
- 图片是否被非等比缩放变形
- 配图色调与整体风格是否协调

## 输出格式

严格按以下格式输出，不要添加额外解释：

**设计类型**：xxx
**图片数量**：X 张（图1 ~ 图X）
**问题总数**：A类 X 条 | B类 X 条 | C类 X 条 | D类 X 条 | E类 X 条 | F类 X 条 | 合计 X 条

---

### A 整体风格一致性（X 条）

**[风格-A01] 图X vs 图Y — 问题标题**
**问题**：具体描述
**建议**：具体修改建议

---

### B 文字可读性（X 条）
（同上格式）

### C 边界与溢出（X 条）
（同上格式）

### D 紧凑度与呼吸感（X 条）
（同上格式）

### E 元素堆叠与层次（X 条）
（同上格式）

### F 图文配合（X 条）
（同上格式）

---

## 注意事项
- 每类问题实事求是，找到几条写几条，不凑数
- 问题定位用"图X + 视觉区域描述"（如"图3 左上角标题行"）
- 修改建议要具体（说"将字号从约16px增大至24px"而非"建议增大字号"）
- 单张图时跳过 A 类
- 没有问题的类别写"未发现问题"
"""

PHASE2_PROMPT_TEMPLATE = """\
你是一名专业的公众号视觉设计质检员。请对以下图片做**深度检查**，重点关注 {category} 方面的问题。

上一轮检查发现了以下疑似问题，请逐一验证并补充细节：
{issues}

请对每条进行：
1. 确认是否真实存在（是/否/存疑）
2. 如果存在，给出更精确的区域定位和量化描述
3. 补充上一轮可能遗漏的问题

输出格式与上一轮一致，只输出本类别的检查结果。
"""

CATEGORY_NAMES = {
    "A": "整体风格一致性",
    "B": "文字可读性",
    "C": "边界与溢出",
    "D": "紧凑度与呼吸感",
    "E": "元素堆叠与层次",
    "F": "图文配合",
}

# ── 图片加载 ──────────────────────────────────────────────────────────

def load_images(paths):
    images = []
    for p in paths:
        try:
            img = Image.open(p)
            images.append(img)
        except Exception as e:
            print(f"  警告：无法加载 {p}：{e}")
    return images

def resolve_image_paths(args):
    if args:
        return [Path(a) for a in args]
    cards_dir = SCRIPT_DIR / "_cards"
    if not cards_dir.exists():
        sys.exit(f"未指定图片且 {cards_dir} 目录不存在")
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    paths = sorted(p for p in cards_dir.iterdir() if p.suffix.lower() in exts)
    if not paths:
        sys.exit(f"{cards_dir} 中没有找到图片文件")
    return paths

# ── Gemini API ────────────────────────────────────────────────────────

def create_gemini_client(cfg):
    from google import genai
    proxy = cfg.get("proxy", "")
    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        print(f"  代理已设置：{proxy}")
    return genai.Client(api_key=cfg["google_api_key"])

def call_gemini(client, model_name, images, prompt):
    contents = [prompt] + images
    response = client.models.generate_content(model=model_name, contents=contents)
    return response.text

# ── Qwen-VL API ──────────────────────────────────────────────────────

def create_qwen_client(cfg):
    from openai import OpenAI
    return OpenAI(
        api_key=cfg["qwen_api_key"],
        base_url=cfg.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    )

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def call_qwen(client, model_name, image_paths, prompt):
    """Qwen-VL 调用：需要原始文件路径做 base64 编码"""
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        data_url = f"data:image/png;base64,{encode_image(p)}"
        content.append({"type": "image_url", "image_url": {"url": data_url}})
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": content}],
    )
    return response.choices[0].message.content

# ── 通用 API 调用 ────────────────────────────────────────────────────

def call_api(provider_info, images, image_paths, prompt):
    """统一调用入口，根据 provider 分发"""
    if provider_info["provider"] == "gemini":
        return call_gemini(provider_info["client"], provider_info["model"], images, prompt)
    elif provider_info["provider"] == "qwen":
        return call_qwen(provider_info["client"], provider_info["model"], image_paths, prompt)
    else:
        sys.exit(f"不支持的 provider: {provider_info['provider']}")

# ── 报告解析 ──────────────────────────────────────────────────────────

def extract_phase1_issues(report_text):
    issues_by_cat = {}
    lines = report_text.split("\n")
    current_cat = None
    current_issues = []

    for line in lines:
        for cat_code in CATEGORY_NAMES:
            header = f"### {cat_code} "
            if line.strip().startswith(header):
                if current_cat and current_issues:
                    issues_by_cat[current_cat] = "\n".join(current_issues)
                current_cat = cat_code
                current_issues = []
                break
        else:
            if current_cat and line.strip().startswith("**["):
                current_issues.append(line.strip())

    if current_cat and current_issues:
        issues_by_cat[current_cat] = "\n".join(current_issues)

    return issues_by_cat

# ── 报告生成 ──────────────────────────────────────────────────────────

def generate_report(phase1_text, phase2_results, image_paths):
    report_lines = [
        "# 公众号贴图验收报告\n",
        f"**图片数量**：{len(image_paths)} 张（图1 ~ 图{len(image_paths)}）",
        f"**验收日期**：{datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]
    report_lines.append(phase1_text)

    if phase2_results:
        report_lines.append("\n---\n")
        report_lines.append("## 深度检查补充\n")
        for cat_code, result in phase2_results.items():
            cat_name = CATEGORY_NAMES.get(cat_code, cat_code)
            report_lines.append(f"### {cat_name} 深度检查\n")
            report_lines.append(result)
            report_lines.append("")

    return "\n".join(report_lines)

# ── 主流程 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="公众号贴图验收工具")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG),
                        help="配置文件路径（默认 qa_config.json）")
    parser.add_argument("images", nargs="*", help="图片路径（不指定则扫描 _cards/）")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    provider = cfg.get("provider", "gemini")
    model_name = cfg.get("model", "gemini-2.0-flash")

    # 创建客户端
    print(f"初始化 {provider.upper()} 客户端（{model_name}）...")
    if provider == "gemini":
        client = create_gemini_client(cfg)
    elif provider == "qwen":
        client = create_qwen_client(cfg)
    else:
        sys.exit(f"不支持的 provider: {provider}")

    provider_info = {"provider": provider, "client": client, "model": model_name}

    # 解析图片
    image_paths = resolve_image_paths(args.images)
    print(f"找到 {len(image_paths)} 张图片：")
    for p in image_paths:
        print(f"  - {p.name}")

    images = load_images(image_paths)
    if not images:
        sys.exit("没有成功加载任何图片")

    is_single = len(images) == 1
    prompt = PHASE1_PROMPT
    if is_single:
        prompt += "\n**当前为单张图，A 类（风格一致性）请跳过并在报告中注明。**"

    # ── Phase 1：全面扫描 ──
    print(f"\n[Phase 1] 进行全面扫描...")
    phase1_text = call_api(provider_info, images, image_paths, prompt)
    print("[Phase 1] 完成\n")

    # ── Phase 2：重点类别深度检查 ──
    phase2_results = {}
    issues_by_cat = extract_phase1_issues(phase1_text)
    cats_to_deep = sorted(issues_by_cat.keys())[:3]

    if cats_to_deep:
        print(f"[Phase 2] 对 {len(cats_to_deep)} 个类别做深度检查：{', '.join(cats_to_deep)}")
        for cat_code in cats_to_deep:
            cat_name = CATEGORY_NAMES.get(cat_code, cat_code)
            print(f"  - {cat_name}...")
            phase2_prompt = PHASE2_PROMPT_TEMPLATE.format(
                category=cat_name,
                issues=issues_by_cat[cat_code],
            )
            result = call_api(provider_info, images, image_paths, phase2_prompt)
            phase2_results[cat_code] = result
        print("[Phase 2] 完成\n")
    else:
        print("[Phase 2] 未发现疑似问题，跳过深度检查\n")

    # ── 生成报告 ──
    report = generate_report(phase1_text, phase2_results, image_paths)

    output_dir = Path(cfg.get("output_dir", "_cards"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"image_qa_{datetime.now().strftime('%m%d')}.md"
    output_file.write_text(report, encoding="utf-8")
    print(f"验收报告已生成：{output_file}")

    print("\n" + "=" * 60)
    print(report.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

# ── 程序化调用入口 ──────────────────────────────────────────────────

def run_qa(config_path=None, image_dir=None):
    """供外部程序调用的 QA 入口。返回 (ok, report_path)。

    config_path: QA 配置文件路径，默认自动探测 qa_config_qwen.json → qa_config.json
    image_dir:   图片目录，默认 _cards/
    """
    script_dir = Path(__file__).parent

    # 自动探测配置文件
    if config_path is None:
        for name in ("qa_config_qwen.json", "qa_config.json"):
            p = script_dir / name
            if p.exists():
                config_path = p
                break
    if config_path is None:
        return True, "跳过 QA：未找到配置文件"

    config_path = Path(config_path)
    if not config_path.exists():
        return True, f"跳过 QA：配置文件不存在 {config_path}"

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    provider = cfg.get("provider", "gemini")

    # 校验 API key
    if provider == "qwen":
        key = cfg.get("qwen_api_key", "")
        if not key or key.startswith("YOUR_"):
            return True, "跳过 QA：未配置 Qwen API Key"
    elif provider == "gemini":
        key = cfg.get("google_api_key", "")
        if not key or key.startswith("YOUR_"):
            return True, "跳过 QA：未配置 Google API Key"

    # 扫描图片
    img_dir = Path(image_dir) if image_dir else script_dir / "_cards"
    if not img_dir.exists():
        return True, f"跳过 QA：图片目录不存在 {img_dir}"
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    image_paths = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in exts)
    if not image_paths:
        return True, f"跳过 QA：{img_dir} 中无图片"

    # 创建客户端
    model_name = cfg.get("model", "gemini-2.0-flash")
    try:
        if provider == "qwen":
            client = create_qwen_client(cfg)
        elif provider == "gemini":
            client = create_gemini_client(cfg)
        else:
            return True, f"跳过 QA：不支持的 provider {provider}"
    except Exception as e:
        return True, f"跳过 QA：客户端初始化失败 - {e}"

    provider_info = {"provider": provider, "client": client, "model": model_name}
    images = load_images(image_paths)

    # Phase 1
    try:
        is_single = len(images) == 1
        prompt = PHASE1_PROMPT
        if is_single:
            prompt += "\n**当前为单张图，A 类（风格一致性）请跳过并在报告中注明。**"
        phase1_text = call_api(provider_info, images, image_paths, prompt)
    except Exception as e:
        return True, f"跳过 QA：Phase 1 调用失败 - {e}"

    # Phase 2
    phase2_results = {}
    issues_by_cat = extract_phase1_issues(phase1_text)
    cats_to_deep = sorted(issues_by_cat.keys())[:3]
    if cats_to_deep:
        try:
            for cat_code in cats_to_deep:
                cat_name = CATEGORY_NAMES.get(cat_code, cat_code)
                phase2_prompt = PHASE2_PROMPT_TEMPLATE.format(
                    category=cat_name, issues=issues_by_cat[cat_code])
                result = call_api(provider_info, images, image_paths, phase2_prompt)
                phase2_results[cat_code] = result
        except Exception as e:
            print(f"  QA Phase 2 部分失败: {e}")

    # 生成报告
    report = generate_report(phase1_text, phase2_results, image_paths)
    output_dir = img_dir
    output_file = output_dir / f"image_qa_{datetime.now().strftime('%m%d')}.md"
    output_file.write_text(report, encoding="utf-8")

    return True, str(output_file)


if __name__ == "__main__":
    main()
