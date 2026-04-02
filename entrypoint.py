#!/usr/bin/env python3
"""
Container startup entry script
Responsibilities:
1. Read TLS certificate content from environment variables and write to certificate file
2. Generate .env configuration file
3. Start main process and keep alive (forward signals, container exits when child process exits)
"""

import os
import signal
import subprocess
import sys


# Certificate content (PEM format string) read from environment variables, written to this path
# Note: K8s YAML >- folded block converts newlines to spaces, need to restore PEM newline format before writing
_ssl_cert_raw = os.environ.get("SSL_CERT_FILE", "")
CERT_CONTENT = _ssl_cert_raw
CERT_OUTPUT_PATH = "./ca-fullchain.pem"


def restore_pem_newlines(pem_content: str) -> str:
    """Restore PEM newline format flattened by YAML >- folded block.

    YAML >- replaces newlines in multi-line content with spaces, corrupting PEM format:
      -----BEGIN CERTIFICATE----- MIID5j... -----END CERTIFICATE-----
    Need to restore to standard PEM format (64-character base64 per line + header/footer on separate lines).
    """
    import re

    # First normalize extra spaces (consecutive spaces become single space, remove leading/trailing whitespace)
    content = " ".join(pem_content.split())

    # Replace spaces between "-----END ... ----- -----BEGIN" with newlines to split multiple certificates
    content = re.sub(r"(-----END [^-]+-----)\s+(-----BEGIN)", r"\1\n\2", content)

    result_parts = []
    # Process each PEM section (BEGIN ... END) one by one
    for match in re.finditer(r"(-----BEGIN [^-]+-----)(.*?)(-----END [^-]+-----)", content, re.DOTALL):
        header = match.group(1).strip()
        body = match.group(2).strip()
        footer = match.group(3).strip()

        # Body may still have spaces (original inline spaces), remove all spaces to get continuous base64
        body_clean = body.replace(" ", "")

        # Split into lines of 64 characters
        body_lines = [body_clean[i:i + 64] for i in range(0, len(body_clean), 64)]

        result_parts.append(header + "\n" + "\n".join(body_lines) + "\n" + footer)

    if result_parts:
        return "\n".join(result_parts) + "\n"

    # If no PEM structure matched, return as-is (may already be in normal format)
    return pem_content

# Main process startup command (passed via environment variable or command line argument)
MAIN_COMMAND = os.environ.get("MAIN_COMMAND", "")

# .env file output path
ENV_FILE_OUTPUT_PATH = os.environ.get("ENV_FILE_OUTPUT_PATH", "./.env")


def write_cert_files():
    """Read public key certificate content from SSL_CERT_FILE environment variable and write to ca-fullchain.pem.
    After writing, update SSL_CERT_FILE environment variable to file path,
    ensuring httpx/ssl libraries read a valid file path instead of certificate content string.
    """
    if not CERT_CONTENT:
        print("[entrypoint] SSL_CERT_FILE environment variable not set, skipping certificate writing")
        return

    cert_dir = os.path.dirname(CERT_OUTPUT_PATH)
    if cert_dir:
        os.makedirs(cert_dir, exist_ok=True)

    # Restore PEM newline format flattened by YAML >- folded block, then write to file
    restored_cert = restore_pem_newlines(CERT_CONTENT)
    with open(CERT_OUTPUT_PATH, "w") as cert_file:
        cert_file.write(restored_cert)

    # Key: Replace environment variable from certificate content to file path
    # httpx will directly read SSL_CERT_FILE as cafile path and pass to ssl.create_default_context
    os.environ["SSL_CERT_FILE"] = os.path.abspath(CERT_OUTPUT_PATH)
    print(f"[entrypoint] Certificate written to: {CERT_OUTPUT_PATH}, SSL_CERT_FILE updated to file path")


def write_env_file():
    """Generate .env configuration file, E2B_API_KEY / E2B_DOMAIN read from environment variables"""
    e2b_api_key = os.environ.get("E2B_API_KEY", "")
    e2b_domain = os.environ.get("E2B_DOMAIN", "agent-vpc.infra")

    env_content = f"""# E2B Environment Variables
# Modify variables according to your actual situation
# Default domain
E2B_DOMAIN={e2b_domain}
# E2B API Key
E2B_API_KEY={e2b_api_key}
# SSL Certificate File
SSL_CERT_FILE=./ca-fullchain.pem
"""

    env_dir = os.path.dirname(ENV_FILE_OUTPUT_PATH)
    if env_dir:
        os.makedirs(env_dir, exist_ok=True)

    with open(ENV_FILE_OUTPUT_PATH, "w") as env_file:
        env_file.write(env_content)
    print(f"[entrypoint] .env file generated: {ENV_FILE_OUTPUT_PATH}")



def start_main_process(command):
    """Start main process, forward signals, script exits when child process exits"""
    if not command:
        print("[entrypoint] MAIN_COMMAND not set, container will keep running (keep-alive mode)")
        keep_alive()
        return

    print(f"[entrypoint] Starting main process: {command}")
    process = subprocess.Popen(command, shell=True)

    # Forward SIGTERM / SIGINT to child process to ensure graceful exit
    def forward_signal(signum, _frame):
        print(f"[entrypoint] Received signal {signum}, forwarding to child process")
        process.send_signal(signum)

    signal.signal(signal.SIGTERM, forward_signal)
    signal.signal(signal.SIGINT, forward_signal)

    exit_code = process.wait()
    print(f"[entrypoint] Main process exited, exit code: {exit_code}")
    sys.exit(exit_code)


def keep_alive():
    """Keep container running when no main process, exit normally after receiving termination signal"""
    def handle_exit(signum, _frame):
        print(f"[entrypoint] Received signal {signum}, container exiting")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_exit)
    signal.signal(signal.SIGINT, handle_exit)

    print("[entrypoint] Container keeping alive, waiting for termination signal...")
    signal.pause()


if __name__ == "__main__":
    print("[entrypoint] Initialization started")

    write_cert_files()
    write_env_file()

    # Support passing main command via command line arguments, higher priority than environment variables
    command = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else MAIN_COMMAND
    start_main_process(command)
