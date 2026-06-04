"""部署到腾讯云 COS 静态网站"""
import sys,os,json
from pathlib import Path
import settings

cwd=settings.CWD
os.chdir(str(cwd))

BUCKET=settings.COS_BUCKET
REGION=settings.COS_REGION
SECRET_ID=settings.COS_SECRET_ID
SECRET_KEY=settings.COS_SECRET_KEY

if SECRET_ID=="你的SecretId":
    print("请先编辑 cos_config.json 填入腾讯云 API 密钥")
    sys.exit(1)

try:
    from qcloud_cos import CosConfig, CosS3Client
except ImportError:
    import subprocess
    subprocess.run([sys.executable,"-m","pip","install","cos-python-sdk-v5","-q"])
    from qcloud_cos import CosConfig, CosS3Client

config=CosConfig(Region=REGION,SecretId=SECRET_ID,SecretKey=SECRET_KEY)
client=CosS3Client(config)

# 确保 Bucket 为公有读
client.put_bucket_acl(Bucket=BUCKET, ACL="public-read")

src=cwd/"_site"
if not src.exists():
    print("_site/ 目录不存在，请先运行 python run.py")
    sys.exit(1)

total=0
for f in sorted(src.rglob("*")):
    if f.is_file():
        key=str(f.relative_to(src)).replace("\\","/")
        client.upload_file(
            Bucket=BUCKET,
            LocalFilePath=str(f),
            Key=key,
            EnableMD5=True,
            ContentDisposition="inline",
            ContentType="text/html; charset=utf-8",
        )
        # 设置对象为公有读
        client.put_object_acl(Bucket=BUCKET, Key=key, ACL="public-read")
        total+=1
        print(f"  [OK] {key}")

print(f"\n完成！上传 {total} 个文件")
print(f"访问地址: https://{BUCKET}.cos-website.{REGION}.myqcloud.com")
