# ⚠️  WARNING: This script is for temporary testing/validation purposes only.
#          DO NOT use in production environments. For cluster testing pod execution.

from dotenv import load_dotenv
import os
import time
import requests
from string import Template
from e2b_code_interpreter import Sandbox


def main():
    print("Hello from openclaw-demo!")
    load_dotenv(override=True)

    # Step 1: Create sandbox
    print("\n[Step 1] Creating sandbox...")
    start_time = time.monotonic()
    sandbox = Sandbox.create(
        'openclaw',
        metadata={
            "e2b.agents.kruise.io/never-timeout": "true"
        }
    )
    print(f"Sandbox creation time: {time.monotonic() - start_time:.2f} seconds")
    print(f"Sandbox ID: {sandbox.sandbox_id}")

    # Read GATEWAY_TOKEN, DASHSCOPE_API_KEY, EXTERNAL_ACCESS_DOMAIN from environment variables
    GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "clawdbot-mode-123456")
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-****")

    # Render openclaw-template.json file and overwrite /root/.openclaw/openclaw.json in sandbox to trigger openclaw restart and config update
    template_path = "openclaw_template.json"
    with open(template_path, "r") as f:
        template_content = f.read()

    rendered_content = Template(template_content).safe_substitute(
        GATEWAY_TOKEN=GATEWAY_TOKEN,
        DASHSCOPE_API_KEY=DASHSCOPE_API_KEY,
    )

    sandbox.files.write("/home/node/.openclaw/openclaw.json", rendered_content, user="node")
    print("file written to /home/node/.openclaw/openclaw.json")
    # Wait a few seconds for service to start
    print("Waiting 30 seconds for gateway to start...")
    time.sleep(30)

    # Step 3: Wait for service to be ready
    print("\n[Step 3] Waiting for service to be ready...")
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
            print(f"Response status code: {response.status_code}")
            if response.status_code == 200:
                print("Service is ready!")
                print(f"Response content: {response.text[:200]}...")  # Print first 200 characters
                ready = True
                break
        except requests.ConnectionError as e:
            print(f"Connection error: {e}")
        except requests.Timeout:
            print("Request timeout, continuing to wait...")
        time.sleep(2)
        print("waiting...")

    print(f"Service is ready, total wait time: {time.monotonic() - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
