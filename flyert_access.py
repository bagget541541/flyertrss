"""Shared request limits and cooldown for every Flyert entry point."""
import functools
import io
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "output"
COOLDOWN_SECONDS = 8 * 60 * 60
MIN_INTERVAL = 6.0
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


class AccessPaused(RuntimeError):
    pass


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def pause(reason, seconds=COOLDOWN_SECONDS):
    path = ROOT / "flyert_cooldown.json"
    old = read_json(path, {}) or {}
    until = max(float(old.get("retry_after", 0)), time.time() + seconds)
    write_json(path, {"reason": reason, "retry_after": until})
    raise AccessPaused(f"{reason}; requests paused until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(until))}")


def check_cooldown():
    # Honor marks written by older detail fetchers, including yesterday's mark.
    paths = [ROOT / "flyert_cooldown.json", *ROOT.glob("threads_detail_*.waf.json")]
    for path in paths:
        state = read_json(path, {}) or {}
        if float(state.get("retry_after", 0)) > time.time():
            raise AccessPaused(f"Flyert cooldown active: {path.name}; retry after {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(state['retry_after'])))}")


@contextmanager
def site_lock():
    """An OS lock releases automatically even if the crawler is terminated."""
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / "flyert_request.lock").open("a+b") as handle:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise AccessPaused("Another Flyert fetch is running; retry after it finishes") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def guarded_main(func):
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        try:
            with site_lock():
                return func(*args, **kwargs)
        except AccessPaused as exc:
            print(f"[PAUSED] {exc}")
            return 2
    return wrapped


def is_blocked(text):
    head = text[:8192].lower()
    return any(value in head for value in (
        "403 forbidden", "access denied", "too many requests",
        "cf-chl-", "checking your browser", "just a moment...",
    ))


def check_response(status, headers, text):
    if status in (403, 429) or is_blocked(text):
        delay = COOLDOWN_SECONDS
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                try:
                    delay = max(delay, parsedate_to_datetime(retry_after).timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
        pause(f"HTTP {status}: blocked or rate limited", delay)
    if status >= 400 or status < 200:
        pause(f"HTTP {status}: fetch failed", 30 * 60)


def before_request():
    check_cooldown()
    path = ROOT / "flyert_last_request.json"
    last = read_json(path, {}) or {}
    remaining = MIN_INTERVAL - (time.time() - float(last.get("time", 0)))
    if remaining > 0:
        time.sleep(remaining)
    write_json(path, {"time": time.time()})


def curl_fetch(url, cookie_file=None):
    before_request()
    cookie_file = cookie_file or ROOT / ".flyert.cookies.txt"
    with tempfile.TemporaryDirectory(prefix="flyert_http_") as temp:
        header_path = Path(temp) / "headers.txt"
        cmd = [
            "curl", "-sSL", "--compressed", "--connect-timeout", "10", "--max-time", "25",
            "--max-redirs", "3", "-A", UA, "-H", "Accept: text/html,application/xhtml+xml",
            "-H", "Accept-Language: zh-CN,zh;q=0.9", "--cookie", str(cookie_file),
            "--cookie-jar", str(cookie_file), "--dump-header", str(header_path), url,
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            pause("curl unavailable or timed out", 30 * 60)
        if result.returncode:
            pause(f"curl network error {result.returncode}", 30 * 60)
        header_blocks = header_path.read_bytes().replace(b"\r\n", b"\n").split(b"\n\n")
        blocks = [block for block in header_blocks if block.startswith(b"HTTP/")]
        if not blocks:
            pause("Missing HTTP response headers", 30 * 60)
        status_line, _, fields = blocks[-1].partition(b"\n")
        status = int(status_line.split()[1])
        headers = BytesParser().parse(io.BytesIO(fields))
        check_response(status, headers, result.stdout.decode("gbk", errors="replace"))
        return result.stdout
