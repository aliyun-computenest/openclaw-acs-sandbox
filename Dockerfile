# ⚠️  声明：本镜像仅用于测试场景临时验证，禁止用于生产环境。
# WARNING: This image is for temporary testing/validation purposes only.
#          DO NOT use in production environments.
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/python:3.11.1

WORKDIR /app

COPY entrypoint.py /app/.internal/entrypoint.py
COPY test_openclaw.py /app/test_openclaw.py
COPY create_openclaw.py /app/create_openclaw.py
COPY openclaw_template.json /app/openclaw_template.json

RUN pip3 install --no-cache-dir python-dotenv requests e2b-code-interpreter e2b-desktop && \
    chmod +x /app/.internal/entrypoint.py

ENTRYPOINT ["python3", "/app/.internal/entrypoint.py"]
