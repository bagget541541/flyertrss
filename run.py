"""飞客信用卡日报 - 一键生成（抓取→富化→发文/卡片）"""
import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import subprocess, sys, os, shutil, argparse, re
from datetime import datetime
from pathlib import Path
import json
import settings

cwd = settings.CWD
os.chdir(str(cwd))

parser = argparse.ArgumentParser(description="飞客信用卡日报 一键生成")
parser.add_argument("--edition", choices=["早报", "晚报"], default=None,
                    help="版次，默认 12:00 前=早报, 12:00 后=晚报")
parser.add_argument("--mode", choices=["simple", "full"], default="simple",
                    help="运行模式: simple(面向发文，仅封面+粘贴版), full(含卡片图+QA+部署)")
parser.add_argument("--resume", action="store_true", help="复用当天本版次列表快照，仅补抓缺失详情")
parser.add_argument("--allow-partial", action="store_true",
                    help="详情覆盖率低于 80%% 但已有超过 10 条时，允许继续生成")
parser.add_argument("--source-date", help="来源日期 YYYY-MM-DD；用于跨天续跑")
args = parser.parse_args()
edition = args.edition
if edition is None:
    hour = datetime.now().hour
    edition = "早报" if hour < 12 else "晚报"


def log(message):
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}")


def _load_run_state():
    try:
        data = json.loads(settings.RUN_STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _commit_success(filtered_posts):
    """提交本轮帖子和成功时间，必须在所有关键步骤完成后调用。"""
    try:
        seen = set(json.loads(settings.SEEN_TIDS_PATH.read_text(encoding="utf-8")))
    except Exception:
        seen = set()
    tids = {str(post.get("tid")) for post in filtered_posts if post.get("tid")}
    seen.update(tids)
    settings.SEEN_TIDS_PATH.write_text(
        json.dumps(sorted(seen), ensure_ascii=False), encoding="utf-8"
    )
    now = datetime.now().astimezone()
    settings.RUN_STATE_PATH.write_text(
        json.dumps({"last_success_at": now.isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log(f"  已提交本轮状态：{len(tids)} 个帖子，成功时间 {now.strftime('%Y-%m-%d %H:%M:%S %z')}")


def _stream_write(prefix, text):
    try:
        sys.stdout.write(prefix + text + "\n")
        sys.stdout.flush()
    except OSError:
        pass


log(f"版次: {edition}   模式: {'完整' if args.mode == 'full' else '简易'}")
state = _load_run_state()
if state.get("last_success_at"):
    try:
        last_success = datetime.fromisoformat(state["last_success_at"])
        elapsed = datetime.now(last_success.tzinfo) - last_success
        hours = elapsed.total_seconds() / 3600
        log(f"距上次成功运行：{hours:.1f} 小时")
        if hours > 24:
            log(f"  ⚠️ 已超过 24 小时，当前时间窗口可能包含较多历史帖子：{hours:.1f} 小时")
    except (TypeError, ValueError):
        log("  ⚠️ 上次成功时间格式无效，本次不使用时间间隔提醒")
else:
    log("尚无成功运行记录，本次作为首次基准运行")


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

    out_thread = threading.Thread(target=_out, args=(proc.stdout,))
    err_thread = threading.Thread(target=_err, args=(proc.stderr,))
    out_thread.start()
    err_thread.start()
    try:
        proc.wait(timeout=step_timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        log(f"  ⏰ {script} 超时 ({step_timeout}s)，已终止")
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        out_thread.join(timeout=2)
        err_thread.join(timeout=2)
    return proc.returncode, lines


def _load_json_list(path):
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("posts"), list):
        return data["posts"]
    return []


print()
print("=" * 54)
print("  飞客信用卡日报")
print("=" * 54)

log("Step 1: 抓取...")
today_key = datetime.now().strftime('%Y%m%d')
source_date = args.source_date or datetime.now().strftime('%Y-%m-%d')
snapshot_path = cwd / "output" / f"run_posts_{today_key}_{edition}.json"
if args.resume:
    if args.source_date:
        snapshot_path = cwd / "output" / f"run_posts_{args.source_date.replace('-', '')}_{edition}.json"
    elif not snapshot_path.exists():
        candidates = sorted(cwd.glob(f"output/run_posts_*_{edition}.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates and sys.stdin.isatty():
            candidate_key = re.search(r"run_posts_(\d{8})_", candidates[0].name).group(1)
            candidate_date = f"{candidate_key[:4]}-{candidate_key[4:6]}-{candidate_key[6:]}"
            answer = input(f"  找到 {candidate_date} 的历史快照，是否作为本次来源日期？输入 y 继续，其他键停止: ").strip().lower()
            if answer in {"y", "yes"}:
                snapshot_path = candidates[0]
                source_date = candidate_date
    filtered_posts = _load_json_list(snapshot_path)
    if filtered_posts:
        settings.FILTERED_PATH.write_text(json.dumps(filtered_posts, ensure_ascii=False, indent=2), encoding="utf-8")
        log("  复用本版次列表快照，不访问论坛列表页")
else:
    fetch_args = ["--defer-seen"]
    if state.get("last_success_at"):
        fetch_args.extend(["--since", state["last_success_at"]])
    rc, _ = _run("fetcher.py", extra_args=fetch_args)
    if rc != 0:
        cached_posts = _load_json_list(snapshot_path)
        if cached_posts and sys.stdin.isatty():
            answer = input("  当前版次有列表快照，是否复用并跳过列表抓取？输入 y 继续，其他键停止: ").strip().lower()
            if answer in {"y", "yes"}:
                filtered_posts = cached_posts
                settings.FILTERED_PATH.write_text(
                    json.dumps(filtered_posts, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                log("  已复用本版次列表快照，不访问论坛列表页")
            else:
                log("  ❌ 抓取失败，停止后续步骤")
                raise SystemExit(rc)
        else:
            log("  ❌ 抓取失败，停止后续步骤")
            raise SystemExit(rc)
    else:
        filtered_posts = _load_json_list(settings.FILTERED_PATH)
        if filtered_posts:
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(filtered_posts, ensure_ascii=False, indent=2), encoding="utf-8")
if not filtered_posts:
    log("  ❌ Step 1 未获取到有效帖子或缺少当天续跑快照，停止后续步骤")
    raise SystemExit(11)

# Freeze the exact posts from this run. The detail fetcher must not infer its
# input from whichever links file happens to sort last in output/.
run_mmdd = source_date[5:7] + source_date[8:10]
run_links_path = cwd / "output" / f"links_{run_mmdd}.json"
run_links_path.parent.mkdir(parents=True, exist_ok=True)
run_links_path.write_text(
    json.dumps(
        [
            {
                "tid": str(post.get("tid", "")),
                "title": post.get("title", ""),
                "url": post.get("url", ""),
                "category": post.get("category", ""),
            }
            for post in filtered_posts
            if post.get("tid") and post.get("url")
        ],
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
log(f"  本轮详情输入: {run_links_path.name} ({len(filtered_posts)} 条)")

# 详情是编辑点评的事实依据。详情抓取失败或覆盖率过低时，禁止继续生成可发布文章，
# 避免文章生成器用通用模板把标题推断伪装成事实点评。
log("Step 1.5: 抓取帖子详情...")
rc, _ = _run(
    "fetch_threads_detail.py",
    step_timeout=900,
    extra_args=[str(run_links_path), "--out-dir", "output"],
)
detail_path = cwd / "output" / f"threads_detail_{run_mmdd}.json"
detail_rows = _load_json_list(detail_path)
expected_tids = {str(post.get("tid")) for post in filtered_posts if post.get("tid")}
detail_ok = {
    str(row.get("tid"))
    for row in detail_rows
    if str(row.get("tid")) in expected_tids and row.get("content", "").strip()
}
coverage = len(detail_ok) / len(expected_tids) if expected_tids else 0
log(f"  详情覆盖率: {len(detail_ok)}/{len(expected_tids)} ({coverage:.0%})")
if rc != 0 or coverage < 0.8:
    failed_tids = sorted(expected_tids - detail_ok)
    if failed_tids:
        log(f"  待补抓失败 tid ({len(failed_tids)}): {','.join(failed_tids)}")
        failed_links_path = cwd / "output" / f"links_{run_mmdd}_failed.json"
        failed_links_path.write_text(
            json.dumps(
                [post for post in filtered_posts
                 if str(post.get("tid")) in set(failed_tids)],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log(f"  已生成失败补抓清单: {failed_links_path.name}")
    can_partial = len(detail_ok) > 10
    allow_partial = args.allow_partial
    if can_partial and not allow_partial and sys.stdin.isatty():
        answer = input("  当前已有超过 10 条详情，是否先生成文章？输入 y 继续，其他键停止: ").strip().lower()
        allow_partial = answer in {"y", "yes"}
    if not (can_partial and allow_partial):
        log("  ❌ 详情抓取失败或覆盖率低于 80%，停止生成文章；请等待 WAF 冷却后只补抓失败 tid")
        raise SystemExit(14)
    log("  ⚠️ 用户允许先生成：文章将标记为部分详情覆盖，缺失 tid 不作为事实依据")
    partial_publish_allowed = can_partial and allow_partial

if args.mode == "full":
    log("Step 2: LLM 富化...")
    rc, _ = _run("enrich.py", step_timeout=600, extra_args=["--edition", edition])
    if rc != 0:
        log("  ❌ enrich 失败，停止后续步骤")
        raise SystemExit(rc)

    enriched_posts = _load_json_list(settings.ENRICHED_PATH)
    if not enriched_posts:
        log("  ❌ Step 2 未生成有效富化数据，停止后续步骤")
        raise SystemExit(12)
else:
    log("Step 2: 跳过 LLM 富化（简易模式直接使用抓取结果）")

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
    full_article_args = [sys.executable, "wechat_article_gen.py", "--publish-mode", "full", "--source-date", source_date]
    if 'partial_publish_allowed' in locals() and partial_publish_allowed:
        full_article_args.append("--allow-partial")
    article_proc = subprocess.run(full_article_args, cwd=cwd)
    if article_proc.returncode != 0:
        log(f"  ⚠️ 公众号文章生成失败，返回码: {article_proc.returncode}")
        raise SystemExit(article_proc.returncode)
    print("=" * 54)
else:
    simple_failed = False
    log("Step 3: 封面生成...")
    rc, _ = _run("cover_gen.py", step_timeout=120)
    if rc != 0:
        simple_failed = True
        log("  ⚠️ 封面生成失败（公众号文章将缺少封面图）")

    print()
    log("Step 4: 公众号文章...")
    article_args = ["--no-cards", "--publish-mode", "simple", "--source-date", source_date]
    if 'partial_publish_allowed' in locals() and partial_publish_allowed:
        article_args.append("--allow-partial")
    rc, _ = _run("wechat_article_gen.py", step_timeout=120, extra_args=article_args)
    if rc != 0:
        simple_failed = True
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
    if simple_failed:
        log("简易模式关键产物生成失败")
        raise SystemExit(13)

_commit_success(filtered_posts)
