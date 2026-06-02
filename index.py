# -*- coding: utf-8 -*-
"""SCF Web 函数 — 从 COS 读取日报并返回完整 HTTP 响应"""
import json, os, sys, mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler

# 手动添加层路径
_layer_path = os.path.join(os.sep, "opt", "python")
if os.path.isdir(_layer_path) and _layer_path not in sys.path:
    sys.path.insert(0, _layer_path)

# COS 配置
COS_BUCKET = os.environ.get("COS_BUCKET", "flyertrss-1257314308")
COS_REGION = os.environ.get("COS_REGION", "ap-guangzhou")
COS_SECRET_ID = os.environ.get("COS_SECRET_ID", "")
COS_SECRET_KEY = os.environ.get("COS_SECRET_KEY", "")

def get_cos_client():
    from qcloud_cos import CosConfig, CosS3Client
    config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
    return CosS3Client(config)

class ProxyHandler(BaseHTTPRequestHandler):
    """COS 代理处理器"""
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        key = path.lstrip("/")
        if ".." in key or key.startswith("/"):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")
            return
        try:
            client = get_cos_client()
            resp = client.get_object(Bucket=COS_BUCKET, Key=key)
            body = resp["Body"].get_raw_stream().read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Disposition", "inline")
            self.send_header("Cache-Control", "public, max-age=600")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"404: " + str(e).encode())

# --- 如果作为主程序直接启动 ---
if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 9000), ProxyHandler)
    print("Starting server on port 9000...")
    server.serve_forever()

