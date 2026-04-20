# ⚠️  声明：本脚本仅用于测试场景临时验证，禁止用于生产环境。集群测试pod运行
# WARNING: This script is for temporary testing/validation purposes only.
#          DO NOT use in production environments.

from dotenv import load_dotenv
import os
import time
import requests
from string import Template
from e2b_code_interpreter import Sandbox


def main():
    print("Hello from openclaw-demo!")
    load_dotenv(override=True)

    # 步骤1: 创建 sandbox
    print("\n[步骤1] 创建 sandbox...")
    start_time = time.monotonic()
    sandbox = Sandbox.create(
        'openclaw',
        metadata={
            "e2b.agents.kruise.io/never-timeout": "true"
        }
    )
    print(f"创建 sandbox 耗时: {time.monotonic() - start_time:.2f} 秒")
    print(f"Sandbox ID: {sandbox.sandbox_id}")

    # 基于环境变量中的 GATEWAY_TOKEN, DASHSCOPE_API_KEY, EXTERNAL_ACCESS_DOMAIN 读取
    GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "clawdbot-mode-123456")
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-****")

    # 渲染 openclaw-template.json 文件， 并将渲染后的文件覆盖沙盒中 /root/.openclaw/openclaw.json 的内容，触发openclaw重启更新配置
    template_path = "openclaw_template.json"
    with open(template_path, "r") as f:
        template_content = f.read()

    rendered_content = Template(template_content).safe_substitute(
        GATEWAY_TOKEN=GATEWAY_TOKEN,
        DASHSCOPE_API_KEY=DASHSCOPE_API_KEY,
    )

    sandbox.files.write("/home/node/.openclaw/openclaw.json", rendered_content, user="node")
    print("已将渲染后的配置写入沙盒 /home/node/.openclaw/openclaw.json")

    # 等待几秒让服务启动
    print("等待 30 秒让 gateway 启动...")
    time.sleep(30)

    # 步骤3: 等待服务就绪
    print("\n[步骤3] 等待服务就绪...")
    host = sandbox.get_host(18789)
    base_url = f"https://{host}"
    print(f"base_url: {base_url}")

    start_time = time.monotonic()
    ready = False
    while True:
        try:
            response = requests.get(
                f"{base_url}/?token={GATEWAY_TOKEN}",
                verify=False,
                timeout=5
            )
            print(f"响应状态码: {response.status_code}")
            if response.status_code == 200:
                print("服务已就绪!")
                print(f"响应内容: {response.text[:200]}...")  # 打印前200字符
                ready = True
                break
        except requests.ConnectionError as e:
            print(f"连接错误: {e}")
        except requests.Timeout:
            print("请求超时，继续等待...")
        time.sleep(2)
        print("waiting...")

    print(f"服务已就绪,等待就绪总耗时: {time.monotonic() - start_time:.2f} 秒")


if __name__ == "__main__":
    main()
