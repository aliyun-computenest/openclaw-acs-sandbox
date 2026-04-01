#!/usr/bin/env python3
"""
⚠️ 声明：本脚本仅用于测试场景临时验证，禁止用于生产环境。
WARNING: This script is for temporary testing/validation purposes only.
         DO NOT use in production environments.

用途：
1. 验证共享 Skills 只读挂载。
2. 验证 OpenClaw 数据备份 -> 镜像升级 -> 数据恢复 的完整流程。

说明：
- 该脚本基于 sandbox-manager REST API 创建/删除 sandbox。
- 通过 kubectl exec 进入实际 Pod 验证挂载、备份和恢复结果。
- 这样可绕开当前测试 Pod 内 E2B SDK 到 envd 的超时问题。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests


class TestFailure(RuntimeError):
    pass


@dataclass
class SandboxInfo:
    sandbox_id: str
    pod_name: str
    template_id: str
    state: str


@dataclass
class FlowArtifacts:
    old_sandbox: Optional[SandboxInfo] = None
    new_sandbox: Optional[SandboxInfo] = None
    config_marker: str = ""
    project_marker: str = ""
    agent_marker: str = ""
    backup_archive_name: str = ""


class OpenClawRestTester:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.artifacts = FlowArtifacts()
        self.api_key = args.api_key or os.environ.get("E2B_API_KEY", "")
        if not self.api_key:
            raise TestFailure("缺少 E2B_API_KEY，请通过 --api-key 或环境变量提供。")

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def step(self, title: str) -> None:
        self.log("")
        self.log("=" * 72)
        self.log(title)
        self.log("=" * 72)

    def run_local(self, cmd: List[str], timeout: int = 120) -> Tuple[int, str, str]:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr

    def kubectl(self, args: List[str], timeout: int = 120) -> Tuple[int, str, str]:
        base = ["kubectl", "--kubeconfig", self.args.kubeconfig]
        return self.run_local(base + args, timeout=timeout)

    def kubectl_exec(
        self,
        pod_name: str,
        command: str,
        *,
        container: str = "sandbox",
        timeout: int = 180,
        check: bool = True,
        retries: int = 1,
    ) -> str:
        last_out = ""
        last_err = ""
        last_rc = 0
        for attempt in range(1, retries + 1):
            args = [
                "exec",
                pod_name,
                "-n",
                self.args.namespace,
                "-c",
                container,
                "--",
                "bash",
                "-lc",
                command,
            ]
            self.log(f"$ kubectl exec {pod_name} -- {command} (attempt {attempt}/{retries})")
            rc, out, err = self.kubectl(args, timeout=timeout)
            last_rc, last_out, last_err = rc, out, err
            if out:
                self.log(out.rstrip())
            if err:
                self.log(err.rstrip())
            if rc == 0 or not check:
                return out

            err_text = f"{out}\n{err}".lower()
            transient = (
                "ttrpc: closed" in err_text
                or "container not found" in err_text
                or "unable to upgrade connection" in err_text
                or "internal error occurred" in err_text
            )
            if transient and attempt < retries:
                self.log("检测到瞬时 exec 错误，等待 Pod 重新就绪后重试...")
                self.wait_pod_ready(pod_name, timeout=min(self.args.wait_ready_timeout, 120))
                time.sleep(5)
                continue
            break

        if check and last_rc != 0:
            raise TestFailure(f"kubectl exec 失败(rc={last_rc}): {command}")
        return last_out

    def rest_create(
        self,
        *,
        template_id: str,
        metadata: Dict[str, str],
        timeout_seconds: int,
    ) -> SandboxInfo:
        body = {
            "templateID": template_id,
            "timeout": timeout_seconds,
            "metadata": metadata,
        }
        self.log(f"创建 sandbox: {json.dumps(body, ensure_ascii=False)}")
        response = requests.post(
            f"{self.args.sandbox_manager_url.rstrip('/')}/sandboxes",
            headers={
                "Content-Type": "application/json",
                "X-API-Key": self.api_key,
            },
            json=body,
            timeout=timeout_seconds + 30,
        )
        if response.status_code not in (200, 201):
            raise TestFailure(f"创建 sandbox 失败: HTTP {response.status_code}, body={response.text[:300]}")
        data = response.json()
        sandbox_id = data["sandboxID"]
        pod_name = sandbox_id.replace("default--", "", 1)
        info = SandboxInfo(
            sandbox_id=sandbox_id,
            pod_name=pod_name,
            template_id=data.get("templateID", template_id),
            state=data.get("state", ""),
        )
        self.log(f"✅ Sandbox 创建成功: {info.sandbox_id}")
        return info

    def rest_delete(self, sandbox: Optional[SandboxInfo]) -> None:
        if sandbox is None:
            return
        self.log(f"删除 sandbox: {sandbox.sandbox_id}")
        response = requests.delete(
            f"{self.args.sandbox_manager_url.rstrip('/')}/sandboxes/{sandbox.sandbox_id}",
            headers={"X-API-Key": self.api_key},
            timeout=30,
        )
        if response.status_code not in (200, 202, 204, 404):
            raise TestFailure(f"删除 sandbox 失败: HTTP {response.status_code}, body={response.text[:300]}")
        self.log(f"删除结果: HTTP {response.status_code}")

    def wait_pod_ready(self, pod_name: str, timeout: int = 300) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            rc, out, err = self.kubectl(
                [
                    "get",
                    "pod",
                    pod_name,
                    "-n",
                    self.args.namespace,
                    "-o",
                    "jsonpath={.status.phase} {.status.containerStatuses[*].ready}",
                ],
                timeout=20,
            )
            if rc == 0:
                text = (out or err).strip()
                if text.startswith("Running") and "false" not in text:
                    self.log(f"Pod 已就绪: {pod_name} => {text}")
                    return
            time.sleep(3)
        raise TestFailure(f"等待 Pod Ready 超时: {pod_name}")

    def build_skills_metadata(self) -> Dict[str, str]:
        volume_config = [
            {
                "pvName": self.args.skills_pv_name,
                "mountPath": self.args.skills_mount_path,
                "subPath": self.args.skills_sub_path,
                "readOnly": True,
            }
        ]
        return {
            "e2b.agents.kruise.io/csi-volume-config": json.dumps(volume_config),
            "e2b.agents.kruise.io/claim-timeout-seconds": str(self.args.claim_timeout),
            "e2b.agents.kruise.io/wait-ready-timeout-seconds": str(self.args.wait_ready_timeout),
        }

    def build_upgrade_metadata(self, image: Optional[str] = None) -> Dict[str, str]:
        volume_config = [
            {
                "pvName": self.args.skills_pv_name,
                "mountPath": self.args.skills_mount_path,
                "subPath": self.args.skills_sub_path,
                "readOnly": True,
            },
            {
                "pvName": self.args.backup_pv_name,
                "mountPath": self.args.backup_mount_path,
                "subPath": self.args.backup_sub_path,
                "readOnly": False,
            },
        ]
        metadata = {
            "e2b.agents.kruise.io/csi-volume-config": json.dumps(volume_config),
            "e2b.agents.kruise.io/claim-timeout-seconds": str(self.args.claim_timeout),
            "e2b.agents.kruise.io/wait-ready-timeout-seconds": str(self.args.wait_ready_timeout),
        }
        if image:
            metadata["e2b.agents.kruise.io/image"] = image
        return metadata

    def verify_skills_readonly(self, sandbox: SandboxInfo) -> None:
        self.step("验证共享 Skills 只读挂载")
        verify_file = f"{self.args.skills_mount_path.rstrip('/')}/{self.args.skills_verify_file.lstrip('/')}"
        content = self.kubectl_exec(sandbox.pod_name, f"cat {verify_file}", timeout=60).strip()
        if self.args.skills_expected_contains and self.args.skills_expected_contains not in content:
            raise TestFailure(f"共享 Skills 内容不符合预期: {verify_file}")

        probe = f"{self.args.skills_mount_path.rstrip('/')}/copilot-readonly-probe.txt"
        self.kubectl_exec(
            sandbox.pod_name,
            f"echo readonly-probe > {probe}",
            timeout=60,
            check=False,
        )
        out = self.kubectl_exec(
            sandbox.pod_name,
            f"test ! -f {probe} && echo readonly-ok",
            timeout=60,
            check=True,
        ).strip()
        if "readonly-ok" not in out:
            raise TestFailure("只读挂载校验失败，探针文件疑似被写入。")
        self.log("✅ 共享 Skills 只读挂载验证通过。")

    def write_user_data(self, sandbox: SandboxInfo) -> None:
        self.step("旧实例写入用户数据")
        ts = int(time.time())
        self.artifacts.config_marker = f"UPGRADE_TEST_CONFIG_V1_{ts}"
        self.artifacts.project_marker = "important-project-data-12345"
        self.artifacts.agent_marker = "custom-agent-code-xyz"
        self.artifacts.backup_archive_name = f"openclaw-state-v1-{ts}.tgz"
        cmd = "\n".join(
            [
                "mkdir -p /root/.openclaw",
                f"echo '{self.artifacts.config_marker}' > /root/.openclaw/config.json",
                f"echo '{self.artifacts.project_marker}' > /root/.openclaw/projects.db",
                f"echo '{self.artifacts.agent_marker}' > /root/.openclaw/agent.py",
                "cat /root/.openclaw/config.json",
                "cat /root/.openclaw/projects.db",
                "cat /root/.openclaw/agent.py",
            ]
        )
        self.kubectl_exec(sandbox.pod_name, cmd, timeout=120)

    def backup_user_data(self, sandbox: SandboxInfo) -> None:
        self.step("备份用户数据到 /backup")
        backup_target = f"{self.args.backup_mount_path.rstrip('/')}/{self.artifacts.backup_archive_name}"
        cmd = "\n".join(
            [
                "cd /root",
                "tar -czf /tmp/openclaw-state-v1.tgz .openclaw",
                f"cp /tmp/openclaw-state-v1.tgz {backup_target}",
                f"ls -la {backup_target}",
            ]
        )
        self.kubectl_exec(sandbox.pod_name, cmd, timeout=180)

    def restore_user_data(self, sandbox: SandboxInfo) -> None:
        self.step("新实例从 /backup 恢复数据")
        backup_target = f"{self.args.backup_mount_path.rstrip('/')}/{self.artifacts.backup_archive_name}"
        cmd = "\n".join(
            [
                "rm -rf /root/.openclaw",
                f"cp {backup_target} /root/{self.artifacts.backup_archive_name}",
                f"tar -xzf /root/{self.artifacts.backup_archive_name} -C /root",
                f"rm -f /root/{self.artifacts.backup_archive_name}",
                "find /root/.openclaw -maxdepth 1 -type f | sort",
            ]
        )
        self.kubectl_exec(sandbox.pod_name, cmd, timeout=180)
        self.log("等待恢复后的 Pod 稳定...")
        self.wait_pod_ready(sandbox.pod_name, timeout=min(self.args.wait_ready_timeout, 180))
        time.sleep(5)

    def verify_restored_data(self, sandbox: SandboxInfo) -> None:
        self.step("验证恢复结果")
        checks = {
            "/root/.openclaw/config.json": self.artifacts.config_marker,
            "/root/.openclaw/projects.db": self.artifacts.project_marker,
            "/root/.openclaw/agent.py": self.artifacts.agent_marker,
        }
        for path, expected in checks.items():
            content = self.kubectl_exec(sandbox.pod_name, f"cat {path}", timeout=60, retries=5).strip()
            if content != expected:
                raise TestFailure(f"恢复文件校验失败: {path}, expected={expected}, actual={content}")

        verify_file = f"{self.args.skills_mount_path.rstrip('/')}/{self.args.skills_verify_file.lstrip('/')}"
        skills = self.kubectl_exec(sandbox.pod_name, f"cat {verify_file}", timeout=60, retries=5).strip()
        if self.args.skills_expected_contains and self.args.skills_expected_contains not in skills:
            raise TestFailure("升级后共享 Skills 校验失败。")

        backup_target = f"{self.args.backup_mount_path.rstrip('/')}/{self.artifacts.backup_archive_name}"
        self.kubectl_exec(sandbox.pod_name, f"test -r {backup_target} && echo backup-readable", timeout=60, retries=5)
        self.log("✅ 备份 -> 升级 -> 恢复 验证通过。")

    def run_skills_readonly(self) -> None:
        sandbox = None
        try:
            sandbox = self.rest_create(
                template_id=self.args.template,
                metadata=self.build_skills_metadata(),
                timeout_seconds=self.args.create_timeout,
            )
            self.wait_pod_ready(sandbox.pod_name, timeout=self.args.wait_ready_timeout)
            self.verify_skills_readonly(sandbox)
        finally:
            if sandbox and self.args.cleanup:
                self.rest_delete(sandbox)

    def run_backup_upgrade_restore(self) -> None:
        try:
            self.artifacts.old_sandbox = self.rest_create(
                template_id=self.args.template,
                metadata=self.build_upgrade_metadata(),
                timeout_seconds=self.args.create_timeout,
            )
            self.wait_pod_ready(self.artifacts.old_sandbox.pod_name, timeout=self.args.wait_ready_timeout)
            self.verify_skills_readonly(self.artifacts.old_sandbox)
            self.write_user_data(self.artifacts.old_sandbox)
            self.backup_user_data(self.artifacts.old_sandbox)

            self.step("释放旧实例")
            self.rest_delete(self.artifacts.old_sandbox)
            self.artifacts.old_sandbox = None
            time.sleep(5)

            self.step("申请新实例并替换镜像")
            self.artifacts.new_sandbox = self.rest_create(
                template_id=self.args.template,
                metadata=self.build_upgrade_metadata(image=self.args.upgrade_image),
                timeout_seconds=self.args.upgrade_timeout,
            )
            self.wait_pod_ready(self.artifacts.new_sandbox.pod_name, timeout=self.args.wait_ready_timeout)
            self.restore_user_data(self.artifacts.new_sandbox)
            self.verify_restored_data(self.artifacts.new_sandbox)
        finally:
            if self.args.cleanup:
                self.rest_delete(self.artifacts.old_sandbox)
                self.rest_delete(self.artifacts.new_sandbox)
                self.artifacts.old_sandbox = None
                self.artifacts.new_sandbox = None

    def run(self) -> None:
        if self.args.mode in ("skills-readonly", "all"):
            self.run_skills_readonly()
        if self.args.mode in ("backup-upgrade-restore", "all"):
            self.run_backup_upgrade_restore()
        self.step("测试完成")
        self.log("✅ 所有选定测试均通过。")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenClaw 共享 Skills / 备份升级恢复 测试脚本（REST 版本）")
    parser.add_argument("--mode", choices=["skills-readonly", "backup-upgrade-restore", "all"], default="all")
    parser.add_argument("--kubeconfig", required=True, help="目标集群 kubeconfig 文件路径")
    parser.add_argument("--api-key", default=os.environ.get("E2B_API_KEY", ""), help="E2B API Key")
    parser.add_argument(
        "--sandbox-manager-url",
        default=os.environ.get("SANDBOX_MANAGER_URL", "http://127.0.0.1:18080"),
        help="sandbox-manager REST 地址",
    )
    parser.add_argument("--namespace", default="default", help="sandbox 所在命名空间")
    parser.add_argument("--template", default="openclaw-more-sbs", help="带 CSI sidecar 的 SandboxSet/Template 名")
    parser.add_argument("--skills-pv-name", default="oss-pv-skills")
    parser.add_argument("--backup-pv-name", default="oss-pv-skills")
    parser.add_argument("--skills-mount-path", default="/skills-part-a")
    parser.add_argument("--skills-sub-path", default="")
    parser.add_argument("--backup-mount-path", default="/backup")
    parser.add_argument("--backup-sub-path", default="/backup")
    parser.add_argument("--skills-verify-file", default="hello-skill.txt")
    parser.add_argument("--skills-expected-contains", default="shared skill")
    parser.add_argument("--upgrade-image", default="ghcr.io/openclaw/openclaw:2026.3.28")
    parser.add_argument("--create-timeout", type=int, default=600)
    parser.add_argument("--upgrade-timeout", type=int, default=600)
    parser.add_argument("--claim-timeout", type=int, default=300)
    parser.add_argument("--wait-ready-timeout", type=int, default=300)
    parser.add_argument("--no-cleanup", dest="cleanup", action="store_false")
    parser.set_defaults(cleanup=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    tester = OpenClawRestTester(args)
    tester.run()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TestFailure as exc:
        print(f"\n❌ 测试失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
