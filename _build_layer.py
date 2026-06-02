# -*- coding: utf-8 -*-
"""打包 Python 3.9 兼容的 SCF 依赖层（cos-sdk + requests + 3.9-safe deps）"""
import os, sys, zipfile, shutil, tempfile, subprocess

cwd = os.path.dirname(os.path.abspath(__file__))
tmpdir = tempfile.mkdtemp()
pkgdir = os.path.join(tmpdir, "python")
os.makedirs(pkgdir, exist_ok=True)

PKGS = [
    "cos-python-sdk-v5==1.8.0",
    "requests==2.28.2",
    "urllib3==1.26.18",
    "charset-normalizer==2.1.1",
    "idna==3.4",
    "certifi==2022.12.7",
    "six==1.16.0",
    "dicttoxml==1.7.16",
    "xmltodict==0.13.0",
    "flask==2.2.5",
    "jinja2==3.1.2",
    "click==8.1.3",
    "itsdangerous==2.1.2",
    "werkzeug==2.2.3",
]

for p in PKGS:
    print(f"  pip install {p} ...")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", p, "-t", pkgdir, "--no-deps"],
        check=True, capture_output=True, text=True
    )

zip_path = os.path.join(cwd, "layer.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(tmpdir):
        for f in files:
            filepath = os.path.join(root, f)
            arcname = os.path.relpath(filepath, tmpdir)
            zf.write(filepath, arcname)

shutil.rmtree(tmpdir)
size_kb = os.path.getsize(zip_path) / 1024
print(f"\n完成: layer.zip ({size_kb:.0f} KB)")

# 验证兼容性
z = zipfile.ZipFile(zip_path)
bad = 0
for n in z.namelist():
    if n.endswith(".py"):
        for i, ln in enumerate(z.read(n).decode(errors="replace").splitlines()):
            if "|" in ln and any(t in ln for t in ["None","str ","int ","bool "]):
                bad += 1
z.close()
if bad == 0:
    print("✅ 完全兼容 Python 3.9")
else:
    print(f"❌ 仍有 {bad} 处 | 语法，需要降级更老版本")
