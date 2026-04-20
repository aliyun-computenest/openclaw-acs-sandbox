from dotenv import load_dotenv
import os
import subprocess
import sys
import time
import traceback
from e2b_code_interpreter import Sandbox

NETWORK_TEST_SCRIPT = r"""#!/bin/bash
# OpenClaw Sandbox 网络隔离测试脚本（直接在 Pod 内执行）

TIMEOUT=5

echo "============================================================"
echo "OpenClaw Sandbox 网络隔离测试"
echo "============================================================"
echo "主机名: $(hostname)"
echo "IP: $(hostname -I 2>/dev/null || echo 'unknown')"
echo "时间: $(date)"
echo "============================================================"

PASS=0
FAIL=0
TOTAL=0

run_test() {
    local test_name="$1"
    local expected="$2"
    local command="$3"

    TOTAL=$((TOTAL + 1))
    echo ""
    echo "------------------------------------------------------------"
    echo "[测试 ${TOTAL}] ${test_name}"
    echo "[命令] ${command}"
    echo "[预期] ${expected}"
    echo "------------------------------------------------------------"

    result=$(eval "${command}" 2>&1) && exit_code=0 || exit_code=$?

    echo "[输出] ${result}"
    echo "[退出码] ${exit_code}"

    if [ "${expected}" = "success" ]; then
        if [ ${exit_code} -eq 0 ]; then
            echo "[结果] ✅ 通过（访问成功，符合预期）"
            PASS=$((PASS + 1))
        else
            echo "[结果] ❌ 失败（访问失败，不符合预期）"
            FAIL=$((FAIL + 1))
        fi
    else
        if [ ${exit_code} -ne 0 ]; then
            echo "[结果] ✅ 通过（访问失败，符合预期 - 网络隔离生效）"
            PASS=$((PASS + 1))
        else
            echo "[结果] ❌ 失败（访问成功，不符合预期 - 网络隔离未生效）"
            FAIL=$((FAIL + 1))
        fi
    fi
}

# 测试 1：公网访问（应成功）
run_test \
    "公网 HTTP 访问 (www.aliyun.com)" \
    "success" \
    "curl -sI --connect-timeout ${TIMEOUT} -m 10 https://www.aliyun.com 2>&1 | head -5"

# 测试 2：DNS 解析（应成功）
run_test \
    "DNS 解析 (www.aliyun.com)" \
    "success" \
    "curl -s --connect-timeout ${TIMEOUT} -o /dev/null -w 'resolved_ip=%{remote_ip}' https://www.aliyun.com && echo ' DNS解析成功'"

# 测试 3：集群内 DNS 解析（应成功 - CoreDNS 可用）
run_test \
    "集群内 DNS 解析: sandbox-gateway.sandbox-system" \
    "success" \
    "RESOLVED_IP=\$(getent hosts sandbox-gateway.sandbox-system.svc.cluster.local 2>/dev/null | awk '{print \$1}'); echo \"resolved_ip=\${RESOLVED_IP}\"; test -n \"\${RESOLVED_IP}\""

# 测试 4：访问 API Server（应失败 - 网络隔离）
run_test \
    "访问 API Server: kubernetes.default:443" \
    "fail" \
    "curl -skv --connect-timeout ${TIMEOUT} -m 10 https://kubernetes.default.svc.cluster.local:443/version 2>&1"

# 测试 5：访问元数据服务（应失败 - 网络隔离）
run_test \
    "访问元数据服务: 100.100.100.200:80" \
    "fail" \
    "curl -s --connect-timeout ${TIMEOUT} -m 10 http://100.100.100.200:80/ 2>&1"

# 测试 6：集群内 Service 访问（应失败 - 网络隔离）
run_test \
    "集群内 Service: sandbox-manager:8080 (manager)" \
    "fail" \
    "curl -s --connect-timeout ${TIMEOUT} -m 10 http://sandbox-manager.sandbox-system:8080/ 2>&1"

run_test \
    "集群内 Service: sandbox-manager:9002 (grpc-extproc)" \
    "fail" \
    "curl -s --connect-timeout ${TIMEOUT} -m 10 http://sandbox-manager.sandbox-system:9002/ 2>&1"

run_test \
    "集群内 Service: sandbox-manager:7788 (http-envoy)" \
    "fail" \
    "curl -s --connect-timeout ${TIMEOUT} -m 10 http://sandbox-manager.sandbox-system:7788/ 2>&1"

run_test \
    "集群内 Service: sandbox-gateway:7788" \
    "fail" \
    "curl -s --connect-timeout ${TIMEOUT} -m 10 http://sandbox-gateway.sandbox-system:7788/ 2>&1"

# 测试总结
echo ""
echo "============================================================"
echo "测试总结"
echo "============================================================"
echo "总测试数: ${TOTAL}"
echo "通过: ${PASS}"
echo "失败: ${FAIL}"
echo "============================================================"

if [ ${FAIL} -eq 0 ]; then
    echo "✅ 所有测试通过！网络隔离验证成功"
    exit 0
else
    echo "❌ 有 ${FAIL} 个测试失败，请检查网络隔离配置"
    exit 1
fi
"""
def create_sandbox(label):
    """创建一个 OpenClaw sandbox 实例"""
    print(f"\n[{label}] 创建 OpenClaw sandbox...")
    start_time = time.monotonic()
    sandbox = Sandbox.create(
        "openclaw",
        timeout=1800,
        envs={
            "GATEWAY_TOKEN": os.environ.get("GATEWAY_TOKEN", "test-token-123456"),
        },
        metadata={
            "e2b.agents.kruise.io/never-timeout": "true",
        },
    )
    elapsed = time.monotonic() - start_time
    print(f"[{label}] Sandbox ID: {sandbox.sandbox_id}")
    print(f"[{label}] 创建耗时: {elapsed:.2f} 秒")
    return sandbox


def get_instance_ip(sandbox, label):
    """获取实例的内网 IP 地址"""
    result = sandbox.commands.run("hostname -I", timeout=10)
    if result.exit_code != 0:
        print(f"[{label}] 获取 IP 失败: {result.stderr}")
        return None
    ips = result.stdout.strip().split()
    for ip in ips:
        if ip.startswith("10.") or ip.startswith("192.168.") or ip.startswith("172."):
            print(f"[{label}] 内网 IP: {ip}")
            return ip
    print(f"[{label}] 未找到内网 IP, 所有 IP: {ips}")
    return ips[0] if ips else None


def upload_and_run_script(sandbox):
    """将 egress 网络隔离测试脚本写入实例并执行"""
    remote_path = "/tmp/test_network_isolation.sh"
    print(f"[上传] 写入测试脚本到实例: {remote_path}")
    sandbox.files.write(remote_path, NETWORK_TEST_SCRIPT)

    print("[执行] 运行 egress 网络隔离测试脚本...")
    print("=" * 60)
    result = sandbox.commands.run(f"bash {remote_path}", timeout=120)
    return result


def run_remote_test(sandbox, test_name, command, expected_success, timeout=15):
    """在 sandbox 实例内执行单条测试

    Args:
        sandbox: Sandbox 实例
        test_name: 测试名称
        command: 要执行的命令
        expected_success: True 表示预期成功，False 表示预期失败
    """
    print(f"\n[测试] {test_name}")
    print(f"[命令] {command}")
    print(f"[预期] {'成功' if expected_success else '失败'}")

    try:
        result = sandbox.commands.run(command, timeout=timeout)
        actual_success = result.exit_code == 0
        print(f"[输出] {result.stdout}")
        if result.stderr:
            print(f"[stderr] {result.stderr}")
        print(f"[退出码] {result.exit_code}")
    except Exception as exc:
        actual_success = False
        print(f"[输出] 命令执行异常: {exc}")
        print(f"[退出码] 非零（异常退出）")

    passed = actual_success == expected_success
    if passed:
        if expected_success:
            print("[结果] ✅ 通过（网络连通，符合预期）")
        else:
            print("[结果] ✅ 通过（网络不通，符合预期 - 网络隔离生效）")
    else:
        if expected_success:
            print("[结果] ❌ 失败（网络不通，不符合预期）")
        else:
            print("[结果] ❌ 失败（网络连通，不符合预期 - 网络隔离未生效）")
    return passed

def run_local_test(test_name, command, expected_success, timeout=10):
    """在运行环境（本地/当前 Pod）执行单条测试

    Args:
        test_name: 测试名称
        command: shell 命令
        expected_success: True 表示预期成功，False 表示预期失败
    """
    print(f"\n[测试] {test_name}")
    print(f"[命令] {command}")
    print(f"[预期] {'成功' if expected_success else '失败'}")

    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        actual_success = proc.returncode == 0
        output = proc.stdout.strip()
        if proc.stderr.strip():
            output += f"\n{proc.stderr.strip()}"
    except subprocess.TimeoutExpired:
        actual_success = False
        output = f"命令超时（{timeout}s）"
    except Exception as exc:
        actual_success = False
        output = f"执行异常: {exc}"

    print(f"[输出] {output}")

    passed = actual_success == expected_success
    if passed:
        if expected_success:
            print("[结果] ✅ 通过（网络连通，符合预期）")
        else:
            print("[结果] ✅ 通过（网络不通，符合预期 - 网络隔离生效）")
    else:
        if expected_success:
            print("[结果] ❌ 失败（网络不通，不符合预期）")
        else:
            print("[结果] ❌ 失败（网络连通，不符合预期 - 网络隔离未生效）")
    return passed


def main():
    print("=" * 60)
    print("OpenClaw Infra 环境网络隔离测试")
    print("=" * 60)

    load_dotenv(override=True)

    results = {}

    # ========================================
    # 步骤 1: 创建两个 OpenClaw sandbox
    # ========================================
    sandbox1 = create_sandbox("实例1")
    sandbox2 = create_sandbox("实例2")

    sandbox1_ip = get_instance_ip(sandbox1, "实例1")
    sandbox2_ip = get_instance_ip(sandbox2, "实例2")

    if not sandbox1_ip or not sandbox2_ip:
        print("\n[错误] 无法获取实例 IP，退出测试")
        sys.exit(1)

    # ========================================
    # 步骤 2: 在实例1内运行 egress 网络隔离测试脚本
    # ========================================
    print("\n" + "=" * 60)
    print("Part 1: 实例1 Egress 网络隔离测试（shell 脚本）")
    print("=" * 60)
    try:
        script_result = upload_and_run_script(sandbox1)
        if script_result.stdout:
            print(script_result.stdout)
        if script_result.stderr:
            print(f"[stderr]\n{script_result.stderr}")
        results["egress网络隔离(shell脚本)"] = script_result.exit_code == 0
    except Exception as error:
        print(f"[错误] 脚本执行失败: {error}")
        print(traceback.format_exc())
        results["egress网络隔离(shell脚本)"] = False

    # ========================================
    # 步骤 3: 从实例1访问实例2的18789端口（预期失败）
    # ========================================
    print("\n" + "=" * 60)
    print("Part 2: 实例间网络隔离测试")
    print("=" * 60)
    results["实例1→实例2:18789(应禁止)"] = run_remote_test(
        sandbox1,
        f"从实例1访问实例2({sandbox2_ip}:18789)",
        f"curl -s --connect-timeout 5 -m 10 http://{sandbox2_ip}:18789/ 2>&1",
        expected_success=False,
    )

    # ========================================
    # 步骤 4: 从运行环境访问实例1的18789端口（预期失败）
    # ========================================
    print("\n" + "=" * 60)
    print("Part 3: 运行环境网络测试")
    print("=" * 60)
    results["运行环境→实例1:18789(应禁止)"] = run_local_test(
        f"从运行环境访问实例1({sandbox1_ip}:18789)",
        f"curl -s --connect-timeout 5 -m 10 http://{sandbox1_ip}:18789/ 2>&1",
        expected_success=False,
    )

    # ========================================
    # 步骤 5: 从运行环境访问 100.100.100.200:80（预期成功）
    # ========================================
    results["运行环境→100.100.100.200:80(应成功)"] = run_local_test(
        "从运行环境访问 100.100.100.200:80",
        "curl -s --connect-timeout 5 -m 10 http://100.100.100.200:80/ 2>&1",
        expected_success=True,
    )

    # ========================================
    # 步骤 6: 从运行环境访问 API Server（预期成功，忽略证书）
    # ========================================
    results["运行环境→apiserver(应成功)"] = run_local_test(
        "从运行环境访问 API Server (kubernetes.default.svc.cluster.local:443)",
        "curl -sk --connect-timeout 5 -m 10 https://kubernetes.default.svc.cluster.local:443/version 2>&1",
        expected_success=True,
    )

    # ========================================
    # 测试总结
    # ========================================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"实例1 ID: {sandbox1.sandbox_id}  IP: {sandbox1_ip}")
    print(f"实例2 ID: {sandbox2.sandbox_id}  IP: {sandbox2_ip}")
    print()

    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 存在失败项，请检查上方输出")
        sys.exit(1)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
