"""飞客信用卡日报 - 一键生成（抓取→富化→发文/卡片）"""
import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import subprocess, sys, os, shutil, argparse
from datetime import datetime
from pathlib import Path
import settings

cwd = settings.CWD
os.chdir(str(cwd))

parser = argparse.ArgumentParser(description="飞客信用卡日报 一键生成")
parser.add_argument("--edition", choices=["早报", "晚报"], default=None,
                    help="版次，默认 12:00 前=早报, 12:00 后=晚报")
parser.add_argument("--mode", choices=["simple", "full"], default="simple",
                    help="运行模式: simple(面向发文，仅封面+粘贴版), full(含卡片图+QA+部署)")
args = parser.parse_args()
edition = args.edition
if edition is None:
    hour = datetime.now().hour
    edition = "早报" if hour < 12 else "晚报"


def log(message):
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}")


def _stream_write(prefix, text):
    try:
        sys.stdout.write(prefix + text + "\n")
        sys.stdout.flush()
    except OSError:
        pass


log(f"版次: {edition}   模式: {'完整' if args.mode == 'full' else '简易'}")


def _run(script, step_timeout=120, extra_args=None):
    """运行子进程（最多等待 step_timeout 秒），流式输出"""
    import threading

    cmd = [sys.executable, script]
    if extra_args:
        cmd.extend(extra_args)
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    lines = []

    def _out(src):
        for line in iter(src.readline, b""):
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            lines.append(decoded)
            _stream_write("  ", decoded)

    def _err(src):
        for line in iter(src.readline, b""):
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            if "Exception" in decoded or "Traceback" in decoded or "Error" in decoded:
                _stream_write("  ! ", decoded)

    threading.Thread(target=_out, args=(proc.stdout,), daemon=True).start()
    threading.Thread(target=_err, args=(proc.stderr,), daemon=True).start()
    try:
        proc.wait(timeout=step_timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        log(f"  ⏰ {script} 超时 ({step_timeout}s)，已终止")
    return proc.returncode, lines


print()
print("=" * 54)
print("  飞客信用卡日报")
print("=" * 54)

log("Step 1: 抓取...")
rc, _ = _run("fetcher.py")
if rc != 0:
    log("  ⚠️ 抓取失败，继续...")

log("Step 2: LLM 富化...")
rc, _ = _run("enrich.py", step_timeout=600, extra_args=["--edition", edition])
if rc != 0:
    log("  ⚠️ enrich 失败，继续...")

if args.mode == "full":
    log("Step 3: 分类+日报...")
    rc, _ = _run("summary.py")
    if rc != 0:
        log("  ⚠️ summary 失败，继续...")

    log("Step 4: 卡片生成...")
    rc, _ = _run("card_gen.py", step_timeout=900)
    if rc != 0:
        log("  ⚠️ card_gen 失败，继续...")

    log("Step 4.5: QA 质检...")
    try:
        from wechat_image_qa import run_qa
        ok, msg = run_qa()
        if ok:
            log(f"  QA 完成: {msg}")
        else:
            log(f"  ⚠️ QA 失败: {msg}")
    except Exception as exc:
        log(f"  ⚠️ QA 跳过: {exc}")

    log("Step 5: 部署预备...")
    ds = datetime.now().strftime("%Y-%m-%d")
    htmls = sorted([name for name in os.listdir(".") if name.startswith("日报_") and name.endswith(".html")], reverse=True)
    if not htmls:
        log("  ⚠️ 未找到日报文件，跳过 index.html 生成")
    else:
        idx = '''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>飞客信用卡日报</title><link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700;900&family=Inter+Tight:wght@400;500;600;700;800&display=swap" rel="stylesheet"><style>*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}body{font-family:"Inter Tight",-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f6f8fa;color:#1e293b;padding:0 0 60px}.hero{background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);color:#fff;padding:44px 0 36px;margin-bottom:28px;position:relative;overflow:hidden}.hero .container{max-width:640px;margin:0 auto;padding:0 20px;position:relative;z-index:1}.hero h1{font-family:"Noto Serif SC",serif;font-size:28px;font-weight:900}.hero h1 span{color:#fbbf24}.hero .sub{display:flex;align-items:center;gap:12px;margin-top:8px;font-size:14px;color:#94a3b8}.container{max-width:640px;margin:0 auto;padding:0 20px}.card{background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04),0 4px 16px rgba(0,0,0,0.04);padding:24px 28px;margin-bottom:16px}.card ul{list-style:none;padding:0}.card li{padding:10px 0;border-bottom:1px solid #f1f5f9;display:flex;align-items:center;gap:12px}.card li:last-child{border-bottom:none}.card li a{color:#1e293b;text-decoration:none;font-weight:500;font-size:15px;transition:color 0.15s}.card li a:hover{color:#4f46e5}.card .idx{font-size:13px;font-weight:700;color:#6366f1;min-width:28px;text-align:right}.footer{text-align:center;padding:32px 16px 0;color:#94a3b8;font-size:13px}@media(max-width:600px){.hero{padding:32px 0 28px}.hero h1{font-size:22px}.container{padding:0 12px}.card{padding:18px 16px;border-radius:12px}.card li a{font-size:14px}}</style></head><body><div class="hero"><div class="container"><h1>飞客<span>信用卡</span>日报</h1><div class="sub">历史归档</div></div></div><div class="container"><div class="card"><ul>'''
        for index, html_name in enumerate(htmls, 1):
            day = html_name.replace("日报_", "").replace(".html", "")
            idx += f'<li><span class="idx">#{index}</span><a href="{html_name}">{day}</a></li>'
        idx += '</ul></div><div class="footer">自动生成 · ' + ds + '</div></body></html>'

        with open("index.html", "w", encoding="utf-8") as fh:
            fh.write(idx)
        log("  index.html（根目录）")

        os.makedirs("_site", exist_ok=True)
        for html_name in htmls:
            shutil.copy2(html_name, os.path.join("_site", html_name))
        with open("_site/index.html", "w", encoding="utf-8") as fh:
            fh.write(idx)

    print()
    log("全部完成！")
    print("=" * 54)
    print()
    log("Step 6: 公众号文章...")
    subprocess.run([sys.executable, "wechat_article_gen.py", "--publish-mode", "full"], cwd=cwd)
    print("=" * 54)
else:
    log("Step 3: 封面生成...")
    rc, _ = _run("cover_gen.py", step_timeout=120)
    if rc != 0:
        log("  ⚠️ 封面生成失败（公众号文章将缺少封面图）")

    print()
    log("Step 4: 公众号文章...")
    rc, _ = _run("wechat_article_gen.py", step_timeout=120, extra_args=["--no-cards", "--publish-mode", "simple"])
    if rc != 0:
        log("  ⚠️ 公众号文章生成失败")
    print("=" * 54)

    log("简易模式完成！输出文件：")
    ds = datetime.now().strftime("%Y-%m-%d")
    article_dir = Path(cwd) / "_site"
    cover_file = Path(cwd) / "_cards" / "cover_wechat.png"
    if cover_file.exists():
        log(f"  📷 封面图: {cover_file}")
    else:
        log("  ⚠️ 封面图未生成，请检查错误日志")
    paste_file = article_dir / f"公众号粘贴版_{ds}.html"
    if paste_file.exists():
        log(f"  📄 粘贴版: {paste_file}")
    else:
        log("  ⚠️ 粘贴版未生成，请检查错误日志")
    print("=" * 54)
    log("提示: 如需卡片图 + QA + 部署，请使用 --mode full")
    print("=" * 54)
