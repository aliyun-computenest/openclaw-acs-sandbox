#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROS Stack 管理工具
通过阿里云CLI调用ROS API创建/删除/查询Stack资源
支持从模板文件和参数文件创建Stack，等待Stack部署完成
支持获取集群 kubeconfig 并保存到本地
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# 环境变量名
ENV_ACCESS_KEY_ID = "ALIYUN_ACCESS_KEY_ID"
ENV_ACCESS_KEY_SECRET = "ALIYUN_ACCESS_KEY_SECRET"
# 兼容旧环境变量名
ENV_ACCESS_KEY_ID_LEGACY = "ALIYUN_COMPUTENEST_AK"
ENV_ACCESS_KEY_SECRET_LEGACY = "ALIYUN_COMPUTENEST_SK"

# Stack 终态状态
STACK_COMPLETE_STATUSES = {
    "CREATE_COMPLETE",
    "UPDATE_COMPLETE",
    "DELETE_COMPLETE",
}

STACK_FAILED_STATUSES = {
    "CREATE_FAILED",
    "UPDATE_FAILED",
    "DELETE_FAILED",
    "ROLLBACK_COMPLETE",
    "ROLLBACK_FAILED",
}


def check_aliyun_cli_installed() -> bool:
    """检查阿里云CLI是否已安装"""
    try:
        result = subprocess.run(
            ["aliyun", "version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_credentials_from_env() -> tuple:
    """从环境变量获取 AK/SK"""
    ak = os.environ.get(ENV_ACCESS_KEY_ID) or os.environ.get(ENV_ACCESS_KEY_ID_LEGACY)
    sk = os.environ.get(ENV_ACCESS_KEY_SECRET) or os.environ.get(ENV_ACCESS_KEY_SECRET_LEGACY)
    return ak, sk


def get_credentials_from_cli_config() -> tuple:
    """从阿里云 CLI 配置文件读取已配置的凭证"""
    config_path = Path.home() / ".aliyun" / "config.json"
    if not config_path.exists():
        return None, None
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 查找 default profile
        for profile in config.get("profiles", []):
            if profile.get("name") == "default":
                return profile.get("access_key_id"), profile.get("access_key_secret")
        
        # 如果没有 default，使用第一个
        if config.get("profiles"):
            profile = config["profiles"][0]
            return profile.get("access_key_id"), profile.get("access_key_secret")
    except Exception as e:
        print(f"警告: 读取 CLI 配置文件失败: {e}")
    
    return None, None


def configure_aliyun_cli(access_key_id: str, access_key_secret: str, region_id: str):
    """配置阿里云CLI认证"""
    print("正在配置阿里云CLI...")
    command = [
        "aliyun", "configure", "set",
        "--profile", "default",
        "--mode", "AK",
        "--access-key-id", access_key_id,
        "--access-key-secret", access_key_secret,
        "--region", region_id,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"配置失败: {result.stderr}")
        sys.exit(1)
    print("阿里云CLI配置成功!")


def run_aliyun_cli(command: List[str]) -> Dict[str, Any]:
    """执行阿里云CLI命令并返回JSON结果"""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"CLI命令执行失败:\n{result.stderr}")
            return {"error": result.stderr}

        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        print(f"JSON解析失败: {error}\n原始输出: {result.stdout}")
        return {"error": str(error)}
    except Exception as error:
        print(f"执行CLI命令时发生错误: {error}")
        return {"error": str(error)}


def load_template(template_path: str) -> str:
    """读取模板文件内容"""
    if not os.path.exists(template_path):
        print(f"模板文件不存在: {template_path}")
        sys.exit(1)
    with open(template_path, "r", encoding="utf-8") as file:
        return file.read()


def extract_template_parameters(template_body: str) -> set:
    """
    从模板内容中提取所有参数名
    
    支持 YAML 和 JSON 格式的 ROS 模板
    
    Returns:
        参数名集合
    """
    try:
        # 尝试解析为 YAML（兼容 JSON）
        if YAML_AVAILABLE:
            template = yaml.safe_load(template_body)
        else:
            template = json.loads(template_body)
        
        parameters = template.get("Parameters", {})
        return set(parameters.keys())
    except Exception as e:
        print(f"警告: 解析模板参数失败: {e}")
        return set()


def resolve_parameter_value(key: str, value: str, base_dir: str) -> tuple:
    """
    解析参数值：如果参数 key 以 'File' 结尾，将 value 视为文件路径并读取其内容，
    同时将传给 ROS 的 ParameterKey 去掉 'File' 后缀（例如 TLSCertFile → TLSCert）。
    文件路径支持相对路径（相对于参数文件所在目录）和绝对路径。

    Args:
        key: 参数名
        value: 参数值（可能是文件路径）
        base_dir: 参数文件所在目录，用于解析相对路径

    Returns:
        (ros_key, resolved_value) 元组：ros_key 是传给 ROS 的参数名，resolved_value 是参数值
    """
    if not key.endswith("File"):
        return key, value

    # File 结尾的 key：传给 ROS 时去掉 File 后缀（例如 TLSCertFile → TLSCert）
    ros_key = key[:-4]

    # 解析文件路径（相对路径基于参数文件目录）
    file_path = value if os.path.isabs(value) else os.path.join(base_dir, value)

    if not os.path.exists(file_path):
        print(f"警告: 参数 '{key}' 指定的文件不存在: {file_path}，将直接使用原始值（ROS key: {ros_key}）")
        return ros_key, value

    with open(file_path, "r", encoding="utf-8") as file:
        file_content = file.read()

    print(f"参数 '{key}' → '{ros_key}': 已读取文件内容 ({file_path}, {len(file_content)} 字节)")
    return ros_key, file_content


def load_parameters(parameters_path: str) -> List[Dict[str, str]]:
    """
    读取参数文件，支持三种格式：
    1. YAML KV 格式（.yaml/.yml）：key: value
    2. ROS 标准格式（.json）：[{"ParameterKey": "k", "ParameterValue": "v"}, ...]
    3. 简化 KV 格式（.json）：{"key": "value", ...}

    特殊处理：
    - 值为 None 的参数（YAML 中注释掉的行）会被自动跳过
    - key 以 'File' 结尾的参数，其值会被视为文件路径并自动读取文件内容
    """
    if not os.path.exists(parameters_path):
        print(f"参数文件不存在: {parameters_path}")
        sys.exit(1)

    parameters_dir = os.path.dirname(os.path.abspath(parameters_path))
    file_ext = os.path.splitext(parameters_path)[1].lower()

    with open(parameters_path, "r", encoding="utf-8") as file:
        if file_ext in (".yaml", ".yml"):
            if not YAML_AVAILABLE:
                print("错误: 读取 YAML 文件需要安装 pyyaml，请执行: pip install pyyaml")
                sys.exit(1)
            data = yaml.safe_load(file)
        else:
            data = json.load(file)

    if isinstance(data, list):
        # 已经是 ROS 标准格式，对 File 结尾的 key 做文件内容解析并去掉 File 后缀
        params = []
        for item in data:
            ros_key, resolved_value = resolve_parameter_value(
                item["ParameterKey"], item["ParameterValue"], parameters_dir
            )
            params.append({"ParameterKey": ros_key, "ParameterValue": resolved_value})
        return params

    if isinstance(data, dict):
        # KV 格式转换为 ROS 标准格式，跳过值为 None 的参数（YAML 中被注释掉的字段）
        params = []
        skipped = []
        for key, value in data.items():
            if value is None:
                skipped.append(key)
                continue
            ros_key, resolved_value = resolve_parameter_value(key, str(value), parameters_dir)
            params.append({"ParameterKey": ros_key, "ParameterValue": resolved_value})
        if skipped:
            print(f"跳过空值参数（未配置）: {', '.join(skipped)}")
        return params

    print(f"参数文件格式不支持，期望 list 或 dict，实际: {type(data)}")
    sys.exit(1)


def get_stack(stack_id: str, region_id: str) -> Dict[str, Any]:
    """查询 Stack 详情"""
    command = [
        "aliyun", "ros", "GetStack",
        "--RegionId", region_id,
        "--StackId", stack_id,
    ]
    return run_aliyun_cli(command)


def _upload_template_to_oss(template_body: str, region_id: str) -> str:
    """上传模板到 OSS 并返回签名 URL，用于绕过 WAF 对 TemplateBody 的拦截。
    
    策略：尝试多个已知 OSS Bucket，优先同区域，然后杭州区域。
    """
    import tempfile
    import time

    # 写入临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write(template_body)
        tmp_path = f.name

    # 候选 Bucket 列表（按优先级）
    candidate_buckets = [
        f"applicationmanager-{region_id}-1563457855438522",
        "applicationmanager-cn-hangzhou-1563457855438522",
    ]

    oss_key = f"ros-templates/ros-template-{int(time.time())}.yaml"

    for bucket in candidate_buckets:
        oss_uri = f"oss://{bucket}/{oss_key}"
        print(f"  尝试上传模板到 {oss_uri} ...")
        cp_result = subprocess.run(
            ["aliyun", "oss", "cp", tmp_path, oss_uri, "--force"],
            capture_output=True, text=True, timeout=120,
        )
        if cp_result.returncode != 0:
            print(f"  上传失败: {cp_result.stderr.strip()[:100]}")
            continue

        # 生成签名 URL（1 小时有效）
        sign_result = subprocess.run(
            ["aliyun", "oss", "sign", oss_uri, "--timeout", "3600"],
            capture_output=True, text=True, timeout=10,
        )
        if sign_result.returncode != 0:
            print(f"  签名失败: {sign_result.stderr.strip()[:100]}")
            continue

        signed_url = sign_result.stdout.strip().split('\n')[0]
        print(f"  模板已上传，签名 URL 已生成")
        os.unlink(tmp_path)
        return signed_url

    os.unlink(tmp_path)
    raise RuntimeError("无法上传模板到任何 OSS Bucket，请检查 OSS 权限")


def create_stack(
    stack_name: str,
    template_body: str,
    parameters: List[Dict[str, str]],
    region_id: str,
    timeout_minutes: int,
    disable_rollback: bool = True,
) -> Dict[str, Any]:
    """创建 ROS Stack
    
    注意：阿里云 CLI 的 --Parameters 是 RepeatList 格式，不是 JSON 数组：
    --Parameters.1.ParameterKey=Key1 --Parameters.1.ParameterValue=Value1
    --Parameters.2.ParameterKey=Key2 --Parameters.2.ParameterValue=Value2
    
    如果 TemplateBody 被 WAF 拦截，自动回退到 OSS 上传 + TemplateURL 方式。
    """
    command = [
        "aliyun", "ros", "CreateStack",
        "--RegionId", region_id,
        "--StackName", stack_name,
        "--TemplateBody", template_body,
    ]
    
    # 将参数列表转换为 RepeatList 格式
    param_args = []
    for idx, param in enumerate(parameters, 1):
        param_args.extend([
            f"--Parameters.{idx}.ParameterKey", param["ParameterKey"],
            f"--Parameters.{idx}.ParameterValue", param["ParameterValue"],
        ])
    command.extend(param_args)
    
    command.extend(["--TimeoutInMinutes", str(timeout_minutes)])
    
    # 失败时不自动回滚，便于排查问题
    if disable_rollback:
        command.extend(["--DisableRollback", "true"])
    
    print(f"正在创建 Stack: {stack_name} (区域: {region_id})...")
    print(f"参数数量: {len(parameters)}")
    result = run_aliyun_cli(command)

    # 检查是否被 WAF 拦截，自动回退到 TemplateURL 方式
    error_msg = result.get("error", "")
    if "SecurityIntercept" in error_msg:
        print("\n[WAF] TemplateBody 被安全服务拦截，自动切换到 OSS TemplateURL 模式...")
        try:
            template_url = _upload_template_to_oss(template_body, region_id)
        except RuntimeError as e:
            print(f"[WAF] OSS 上传失败: {e}")
            return result

        # 用 TemplateURL 重建命令
        command_url = [
            "aliyun", "ros", "CreateStack",
            "--RegionId", region_id,
            "--StackName", stack_name,
            "--TemplateURL", template_url,
        ]
        command_url.extend(param_args)
        command_url.extend(["--TimeoutInMinutes", str(timeout_minutes)])
        if disable_rollback:
            command_url.extend(["--DisableRollback", "true"])

        print(f"[WAF] 使用 TemplateURL 重新创建 Stack...")
        result = run_aliyun_cli(command_url)

    return result


def delete_stack(stack_id: str, region_id: str) -> Dict[str, Any]:
    """删除 ROS Stack"""
    command = [
        "aliyun", "ros", "DeleteStack",
        "--RegionId", region_id,
        "--StackId", stack_id,
    ]
    print(f"正在删除 Stack: {stack_id} (区域: {region_id})...")
    return run_aliyun_cli(command)


def list_stacks(region_id: str, stack_name: str = "") -> Dict[str, Any]:
    """列出 Stack，可按名称过滤"""
    command = [
        "aliyun", "ros", "ListStacks",
        "--RegionId", region_id,
    ]
    if stack_name:
        command += ["--StackName", f'["{stack_name}"]']
    return run_aliyun_cli(command)


def list_stack_events(stack_id: str, region_id: str, status_filter: str = "") -> Dict[str, Any]:
    """列出 Stack 事件"""
    command = [
        "aliyun", "ros", "ListStackEvents",
        "--RegionId", region_id,
        "--StackId", stack_id,
        "--PageSize", "50",
    ]
    if status_filter:
        command += ["--Status", f'["{status_filter}"]']
    return run_aliyun_cli(command)


def get_first_failure_event(stack_id: str, region_id: str) -> Optional[Dict[str, Any]]:
    """获取 Stack 第一个 CREATE_FAILED 事件（根因分析）"""
    result = list_stack_events(stack_id, region_id)
    if "error" in result:
        return None
    
    events = result.get("Events", [])
    # 筛选 CREATE_FAILED 事件并按时间排序
    failed_events = [e for e in events if e.get("Status") == "CREATE_FAILED"]
    if not failed_events:
        return None
    
    # 按 CreateTime 排序，找最早的
    failed_events.sort(key=lambda x: x.get("CreateTime", ""))
    return failed_events[0] if failed_events else None


def list_available_eips(region_id: str) -> List[Dict[str, Any]]:
    """列出可用的 EIP"""
    command = [
        "aliyun", "vpc", "DescribeEipAddresses",
        "--RegionId", region_id,
        "--PageSize", "50",
    ]
    result = run_aliyun_cli(command)
    if "error" in result:
        return []
    
    eips = result.get("EipAddresses", {}).get("EipAddress", [])
    # 只返回可用状态的 EIP
    return [eip for eip in eips if eip.get("Status") == "Available"]


def bind_eip_to_cluster(cluster_id: str, eip_id: str, region_id: str) -> Dict[str, Any]:
    """绑定 EIP 到集群 API Server"""
    command = [
        "aliyun", "cs", "ModifyCluster",
        "--ClusterId", cluster_id,
        "--region", region_id,
        "--body", json.dumps({"api_server_eip_id": eip_id}),
    ]
    print(f"正在绑定 EIP {eip_id} 到集群 {cluster_id}...")
    return run_aliyun_cli(command)


def wait_for_stack(stack_id: str, region_id: str, timeout_seconds: int) -> Dict[str, Any]:
    """轮询等待 Stack 达到终态"""
    start_time = time.time()
    poll_interval = 15

    while time.time() - start_time < timeout_seconds:
        result = get_stack(stack_id, region_id)

        if "error" in result:
            print(f"查询 Stack 状态失败: {result['error']}")
            time.sleep(poll_interval)
            continue

        status = result.get("Status", "")
        status_reason = result.get("StatusReason", "")
        elapsed = int(time.time() - start_time)

        print(f"[{elapsed}s] Stack {stack_id} 状态: {status}"
              + (f" - {status_reason}" if status_reason else ""))

        if status in STACK_COMPLETE_STATUSES:
            return result

        if status in STACK_FAILED_STATUSES:
            print(f"Stack 操作失败，状态: {status}")
            # 打印第一个失败事件（根因）
            first_failure = get_first_failure_event(stack_id, region_id)
            if first_failure:
                print("\n" + "=" * 60)
                print("【根因分析】第一个失败的资源:")
                print(f"  资源: {first_failure.get('LogicalResourceId', 'N/A')}")
                print(f"  时间: {first_failure.get('CreateTime', 'N/A')}")
                print(f"  原因: {first_failure.get('StatusReason', 'N/A')}")
                print("=" * 60)
            return result

        time.sleep(poll_interval)

    print(f"等待超时（{timeout_seconds}s），Stack 未达到终态")
    return get_stack(stack_id, region_id)


def print_stack_outputs(stack_detail: Dict[str, Any]):
    """打印 Stack 的 Outputs"""
    outputs = stack_detail.get("Outputs", [])
    if not outputs:
        return

    print("\n" + "=" * 60)
    print("Stack Outputs:")
    print("=" * 60)
    for output in outputs:
        key = output.get("OutputKey", "")
        value = output.get("OutputValue", "")
        description = output.get("Description", "")
        print(f"  {key}: {value}")
        if description:
            print(f"    ({description})")
    print("=" * 60)


def get_cluster_id_from_stack(stack_detail: Dict[str, Any]) -> Optional[str]:
    """从 Stack Outputs 中提取 ClusterId"""
    outputs = stack_detail.get("Outputs", [])
    for output in outputs:
        key = output.get("OutputKey", "")
        # 查找包含 ClusterId 的输出
        if "ClusterId" in key or key == "ClusterId":
            return output.get("OutputValue")
    return None


def get_kubeconfig(cluster_id: str, region_id: str, private_ip: bool = False) -> Optional[str]:
    """获取集群的 kubeconfig"""
    command = [
        "aliyun", "cs", "DescribeClusterUserKubeconfig",
        "--ClusterId", cluster_id,
        "--region", region_id,
    ]
    if private_ip:
        command.extend(["--PrivateIpAddress", "true"])
    else:
        command.extend(["--PrivateIpAddress", "false"])
    
    print(f"正在获取集群 {cluster_id} 的 kubeconfig...")
    result = run_aliyun_cli(command)
    
    if "error" in result:
        print(f"获取 kubeconfig 失败: {result['error']}")
        return None
    
    config = result.get("config")
    if not config:
        print(f"响应中未找到 config 字段: {result}")
        return None
    
    return config


def save_kubeconfig(kubeconfig: str, output_path: str = None) -> str:
    """保存 kubeconfig 到文件"""
    if output_path is None:
        output_path = str(Path.home() / ".kube" / "config")
    
    # 确保目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # 备份现有文件
    if os.path.exists(output_path):
        backup_path = f"{output_path}.backup"
        print(f"备份现有 kubeconfig 到: {backup_path}")
        with open(output_path, "r", encoding="utf-8") as f:
            with open(backup_path, "w", encoding="utf-8") as bf:
                bf.write(f.read())
    
    # 写入新的 kubeconfig
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(kubeconfig)
    
    print(f"kubeconfig 已保存到: {output_path}")
    return output_path


def find_conflicting_privatezone(zone_name: str, vpc_id: str, region_id: str) -> Optional[Dict[str, Any]]:
    """
    检测指定 VPC 下是否已绑定同名 PrivateZone。

    使用 DescribeZones 的 QueryVpcId 参数直接按 VPC 过滤，一次调用即可完成检测。
    PrivateZone 限制：同一 VPC 内不能绑定两个同名 Zone（ZoneVpc.Zone.Repeated）。
    在 ExistingVPC 场景下，旧 Stack 删除后 Zone 可能残留并仍绑定着该 VPC，
    导致新 Stack 创建时 PrivateZoneVpcBinder 失败。

    Returns:
        冲突的 Zone 信息字典（含 ZoneId、ZoneName），无冲突时返回 None
    """
    result = run_aliyun_cli([
        "aliyun", "pvtz", "DescribeZones",
        "--RegionId", region_id,
        "--SearchMode", "EXACT",
        "--Keyword", zone_name,
        "--QueryVpcId", vpc_id,
        "--QueryRegionId", region_id,
        "--PageSize", "10",
    ])
    if "error" in result:
        print(f"[预检] 查询 PrivateZone 失败（跳过预检）: {result['error']}")
        return None

    zones = result.get("Zones", {}).get("Zone", [])
    for zone in zones:
        if zone.get("ZoneName") == zone_name:
            return {"ZoneId": zone["ZoneId"], "ZoneName": zone["ZoneName"]}
    return None


def unbind_privatezone_vpc(zone_id: str, vpc_id: str, region_id: str) -> bool:
    """
    解绑 PrivateZone 与指定 VPC 的绑定关系。

    通过传入空 Vpcs 列表实现全量解绑（BindZoneVpc 是覆盖语义）。
    用于清理旧 Stack 残留的 Zone-VPC 绑定，避免新 Stack 创建时报 ZoneVpc.Zone.Repeated。

    Returns:
        True 表示解绑成功，False 表示失败
    """
    result = run_aliyun_cli([
        "aliyun", "pvtz", "BindZoneVpc",
        "--RegionId", region_id,
        "--ZoneId", zone_id,
        "--Vpcs", "[]",
    ])
    if "error" in result:
        print(f"[预检] 解绑 PrivateZone VPC 失败: {result['error']}")
        return False
    return True


def precheck_privatezone_conflicts(parameters: List[Dict[str, str]], region_id: str):
    """
    在创建 Stack 前预检 PrivateZone VPC 绑定状态（仅检测，不自动解绑）。

    触发条件（同时满足）：
    - EnablePrivateZone 参数为 true
    - VpcId 参数有值（ExistingVPC 场景）

    模板中已有 UseExistingPrivateZoneCondition 逻辑来处理已有 Zone 的情况：
    - 如果 Zone 已存在且绑定了该 VPC，模板会走 ExistingPrivateZone 分支，
      查询已有 Zone 的 BindVpcs 并追加新 VPC 重新绑定（幂等操作）。
    - 如果 Zone 不存在，模板会走 CreateNewPrivateZone 分支创建新 Zone。

    因此预检不应解绑 VPC，否则会导致 ExistingVpcZones（通过 VpcId 查询）
    查不到已有 Zone，使后续 Jq 操作返回 null 导致 Stack 创建失败。
    """
    param_map = {p["ParameterKey"]: p["ParameterValue"] for p in parameters}

    enable_private_zone = param_map.get("EnablePrivateZone", "false").lower()
    vpc_id = param_map.get("VpcId", "")
    zone_name = param_map.get("E2BDomainAddress", "")

    if enable_private_zone != "true" or not vpc_id or not zone_name:
        return

    print(f"\n[预检] 检测 PrivateZone 状态: 域名={zone_name}, VPC={vpc_id}")
    conflict = find_conflicting_privatezone(zone_name, vpc_id, region_id)

    if not conflict:
        print(f"[预检] 未发现已有同名 Zone 绑定该 VPC，模板将创建新 Zone")
    else:
        zone_id = conflict["ZoneId"]
        print(f"[预检] 发现已有 Zone '{zone_name}' (ZoneId={zone_id}) 已绑定 VPC {vpc_id}")
        print(f"[预检] 模板将复用已有 Zone 并追加绑定新 VPC（UseExistingPrivateZoneCondition）")


def cmd_create(args, region_id: str):
    """执行 create 子命令"""
    template_body = load_template(args.template)
    parameters = load_parameters(args.parameters) if args.parameters else []

    # 从模板中提取参数名，过滤掉不在模板中定义的参数
    template_params = extract_template_parameters(template_body)
    if template_params:
        filtered_params = []
        skipped_params = []
        for param in parameters:
            param_key = param["ParameterKey"]
            if param_key in template_params:
                filtered_params.append(param)
            else:
                skipped_params.append(param_key)
        
        if skipped_params:
            print(f"跳过不在模板中定义的参数: {', '.join(skipped_params)}")
        parameters = filtered_params

    # 预检：PrivateZone VPC 绑定冲突（ExistingVPC 场景下旧 Stack 残留问题）
    precheck_privatezone_conflicts(parameters, region_id)

    print(f"模板文件: {args.template}")
    print(f"参数文件: {args.parameters or '(无)'}")
    print(f"参数数量: {len(parameters)}")
    print("-" * 60)

    result = create_stack(
        stack_name=args.stack_name,
        template_body=template_body,
        parameters=parameters,
        region_id=region_id,
        timeout_minutes=args.timeout_minutes,
        disable_rollback=not args.enable_rollback,
    )

    if "error" in result:
        print(f"创建 Stack 失败: {result['error']}")
        sys.exit(1)

    stack_id = result.get("StackId", "")
    if not stack_id:
        print(f"创建返回异常，未获取到 StackId: {result}")
        sys.exit(1)

    print(f"Stack 创建请求已提交，StackId: {stack_id}")

    if args.no_wait:
        print("已跳过等待（--no-wait），Stack 正在后台部署中")
        return stack_id

    timeout_seconds = args.timeout_minutes * 60
    print(f"\n等待 Stack 部署完成（超时: {args.timeout_minutes} 分钟）...")
    final_result = wait_for_stack(stack_id, region_id, timeout_seconds)

    status = final_result.get("Status", "Unknown")
    print(f"\nStack 最终状态: {status}")
    print_stack_outputs(final_result)

    if status not in STACK_COMPLETE_STATUSES:
        sys.exit(1)
    
    # 如果启用了获取 kubeconfig，则获取并保存
    if getattr(args, 'kubeconfig', False):
        cluster_id = get_cluster_id_from_stack(final_result)
        if cluster_id:
            kubeconfig = get_kubeconfig(cluster_id, region_id, private_ip=False)
            if kubeconfig:
                save_kubeconfig(kubeconfig, args.kubeconfig_output)
                print(f"\n可以使用 kubectl 访问集群: kubectl get nodes")
        else:
            print("警告: 未能从 Stack Outputs 中获取 ClusterId，跳过 kubeconfig 获取")
    
    return stack_id


def cmd_delete(args, region_id: str):
    """执行 delete 子命令"""
    stack_id = args.stack_id

    # 判断是 Stack ID 还是名称（UUID 格式的是 ID）
    import re
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
    if not uuid_pattern.match(stack_id):
        print(f"按名称查询 Stack: {stack_id}")
        list_result = list_stacks(region_id, stack_name=stack_id)
        stacks = list_result.get("Stacks", [])
        if not stacks:
            print(f"未找到名称为 '{stack_id}' 的 Stack")
            sys.exit(1)
        stack_id = stacks[0]["StackId"]
        print(f"找到 StackId: {stack_id}")

    result = delete_stack(stack_id, region_id)

    if "error" in result:
        print(f"删除 Stack 失败: {result['error']}")
        sys.exit(1)

    print(f"Stack 删除请求已提交: {stack_id}")

    if args.no_wait:
        print("已跳过等待（--no-wait），Stack 正在后台删除中")
        return

    timeout_seconds = args.timeout_minutes * 60
    print(f"\n等待 Stack 删除完成（超时: {args.timeout_minutes} 分钟）...")
    final_result = wait_for_stack(stack_id, region_id, timeout_seconds)

    status = final_result.get("Status", "Unknown")
    print(f"\nStack 最终状态: {status}")

    if status not in STACK_COMPLETE_STATUSES:
        sys.exit(1)


def cmd_get(args, region_id: str):
    """执行 get 子命令"""
    stack_id = args.stack_id

    # 判断是 Stack ID 还是名称（UUID 格式的是 ID）
    import re
    uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
    if not uuid_pattern.match(stack_id):
        print(f"按名称查询 Stack: {stack_id}")
        list_result = list_stacks(region_id, stack_name=stack_id)
        stacks = list_result.get("Stacks", [])
        if not stacks:
            print(f"未找到名称为 '{stack_id}' 的 Stack")
            sys.exit(1)
        stack_id = stacks[0]["StackId"]

    result = get_stack(stack_id, region_id)

    if "error" in result:
        print(f"查询 Stack 失败: {result['error']}")
        sys.exit(1)

    status = result.get("Status", "")
    status_reason = result.get("StatusReason", "")
    create_time = result.get("CreateTime", "")
    update_time = result.get("UpdateTime", "")

    print(f"\nStack 详情:")
    print(f"  StackId:    {result.get('StackId', '')}")
    print(f"  StackName:  {result.get('StackName', '')}")
    print(f"  Status:     {status}" + (f" - {status_reason}" if status_reason else ""))
    print(f"  CreateTime: {create_time}")
    print(f"  UpdateTime: {update_time}")
    print_stack_outputs(result)


def cmd_kubeconfig(args, region_id: str):
    """执行 kubeconfig 子命令 - 获取集群 kubeconfig"""
    cluster_id = args.cluster_id
    
    # 如果提供的是 Stack 名称/ID，从 Stack 获取 ClusterId
    if args.from_stack:
        stack_id = args.from_stack
        if not stack_id.startswith("stack-"):
            list_result = list_stacks(region_id, stack_name=stack_id)
            stacks = list_result.get("Stacks", [])
            if not stacks:
                print(f"未找到名称为 '{stack_id}' 的 Stack")
                sys.exit(1)
            stack_id = stacks[0]["StackId"]
        
        stack_detail = get_stack(stack_id, region_id)
        if "error" in stack_detail:
            print(f"查询 Stack 失败: {stack_detail['error']}")
            sys.exit(1)
        
        cluster_id = get_cluster_id_from_stack(stack_detail)
        if not cluster_id:
            print("未能从 Stack Outputs 中获取 ClusterId")
            sys.exit(1)
        print(f"从 Stack 获取到 ClusterId: {cluster_id}")
    
    if not cluster_id:
        print("错误: 请提供 --cluster-id 或 --from-stack 参数")
        sys.exit(1)
    
    kubeconfig = get_kubeconfig(cluster_id, region_id, private_ip=args.private_ip)
    if not kubeconfig:
        sys.exit(1)
    
    output_path = save_kubeconfig(kubeconfig, args.output)
    
    # 验证集群连接
    print(f"\n验证集群连接...")
    result = subprocess.run(
        ["kubectl", "get", "nodes", "--request-timeout=10s"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        print(result.stdout)
        return
    
    # 连接失败，检查是否是内网 IP 问题
    if "timeout" in result.stderr.lower() or "connection refused" in result.stderr.lower():
        print(f"连接失败: {result.stderr}")
        print("\n检测到连接超时，可能是 kubeconfig 使用了内网 IP")
        
        if args.auto_bind_eip:
            # 自动绑定 EIP
            print("\n尝试自动绑定 EIP...")
            eips = list_available_eips(region_id)
            if not eips:
                print("错误: 没有可用的 EIP，请先申请 EIP")
                sys.exit(1)
            
            eip = eips[0]
            print(f"找到可用 EIP: {eip.get('IpAddress')} ({eip.get('AllocationId')})")
            
            bind_result = bind_eip_to_cluster(cluster_id, eip.get("AllocationId"), region_id)
            if "error" in bind_result:
                print(f"绑定 EIP 失败: {bind_result['error']}")
                sys.exit(1)
            
            print("EIP 绑定成功，等待 10 秒后重新获取 kubeconfig...")
            time.sleep(10)
            
            # 重新获取 kubeconfig
            kubeconfig = get_kubeconfig(cluster_id, region_id, private_ip=False)
            if kubeconfig:
                save_kubeconfig(kubeconfig, args.output)
                print("\n重新验证集群连接:")
                os.system("kubectl get nodes")
        else:
            print("\n提示: 可以使用 --auto-bind-eip 参数自动绑定 EIP")
            print("或手动执行以下命令绑定 EIP:")
            print(f"  # 查询可用 EIP")
            print(f"  aliyun vpc DescribeEipAddresses --RegionId {region_id} --PageSize 50")
            print(f"  # 绑定 EIP")
            print(f"  aliyun cs ModifyCluster --ClusterId {cluster_id} --region {region_id} --body '{{\"api_server_eip_id\": \"<eip-id>\"}}'")
    else:
        print(f"连接失败: {result.stderr}")


def main():
    parser = argparse.ArgumentParser(
        description="ROS Stack 管理工具 - 通过模板文件创建/删除/查询 Stack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 方式一：使用已配置的阿里云 CLI 凭证（推荐）
  python ros_stack_manager.py create --stack-name my-stack --template template.yaml --parameters parameters.yaml --region cn-beijing

  # 方式二：通过环境变量提供 AK/SK
  export ALIYUN_ACCESS_KEY_ID=YOUR_AK
  export ALIYUN_ACCESS_KEY_SECRET=YOUR_SK
  python ros_stack_manager.py create --stack-name my-stack --template template.yaml --region cn-beijing

  # 创建 Stack 并获取 kubeconfig
  python ros_stack_manager.py create --stack-name my-stack --template template.yaml --kubeconfig --region cn-beijing

  # 单独获取 kubeconfig
  python ros_stack_manager.py kubeconfig --cluster-id cxxx --region cn-beijing
  python ros_stack_manager.py kubeconfig --from-stack my-stack --region cn-beijing

  # 删除 Stack
  python ros_stack_manager.py delete --stack-id my-stack --region cn-beijing
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")
    subparsers.required = True

    # 公共参数 parent parser
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--region", "-r",
        default="cn-beijing",
        help="阿里云区域 (默认: cn-beijing)",
    )
    common_parser.add_argument(
        "--ak",
        default="",
        help=f"阿里云 Access Key ID（也可通过环境变量 {ENV_ACCESS_KEY_ID} 设置）",
    )
    common_parser.add_argument(
        "--sk",
        default="",
        help=f"阿里云 Access Key Secret（也可通过环境变量 {ENV_ACCESS_KEY_SECRET} 设置）",
    )

    # create 子命令
    create_parser = subparsers.add_parser(
        "create", help="创建 ROS Stack", parents=[common_parser]
    )
    create_parser.add_argument("--stack-name", "-n", required=True, help="Stack 名称")
    create_parser.add_argument("--template", "-t", required=True, help="ROS 模板文件路径（YAML/JSON）")
    create_parser.add_argument(
        "--parameters", "-p",
        default="",
        help="参数文件路径，支持 ROS 标准格式或简化 KV 格式",
    )
    create_parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=60,
        help="Stack 创建超时时间（分钟，默认: 60）",
    )
    create_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="提交后不等待 Stack 部署完成",
    )
    create_parser.add_argument(
        "--enable-rollback",
        action="store_true",
        help="失败时自动回滚（默认不回滚，便于排查问题）",
    )
    create_parser.add_argument(
        "--kubeconfig",
        action="store_true",
        help="部署完成后获取集群 kubeconfig",
    )
    create_parser.add_argument(
        "--kubeconfig-output",
        default=None,
        help="kubeconfig 保存路径（默认: ~/.kube/config）",
    )

    # delete 子命令
    delete_parser = subparsers.add_parser(
        "delete", help="删除 ROS Stack", parents=[common_parser]
    )
    delete_parser.add_argument(
        "--stack-id", "-s",
        required=True,
        help="Stack ID 或 Stack 名称",
    )
    delete_parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=30,
        help="等待删除完成的超时时间（分钟，默认: 30）",
    )
    delete_parser.add_argument(
        "--no-wait",
        action="store_true",
        help="提交后不等待 Stack 删除完成",
    )

    # get 子命令
    get_parser = subparsers.add_parser(
        "get", help="查询 ROS Stack 详情", parents=[common_parser]
    )
    get_parser.add_argument(
        "--stack-id", "-s",
        required=True,
        help="Stack ID 或 Stack 名称",
    )

    # kubeconfig 子命令
    kubeconfig_parser = subparsers.add_parser(
        "kubeconfig", help="获取集群 kubeconfig", parents=[common_parser]
    )
    kubeconfig_parser.add_argument(
        "--cluster-id", "-c",
        default="",
        help="集群 ID",
    )
    kubeconfig_parser.add_argument(
        "--from-stack",
        default="",
        help="从 Stack 获取 ClusterId（Stack ID 或名称）",
    )
    kubeconfig_parser.add_argument(
        "--private-ip",
        action="store_true",
        help="使用内网地址访问集群",
    )
    kubeconfig_parser.add_argument(
        "--output", "-o",
        default=None,
        help="kubeconfig 保存路径（默认: ~/.kube/config）",
    )
    kubeconfig_parser.add_argument(
        "--auto-bind-eip",
        action="store_true",
        help="连接失败时自动绑定可用 EIP 到集群",
    )

    args = parser.parse_args()

    # 检查 CLI 是否安装
    if not check_aliyun_cli_installed():
        print("错误: 未检测到阿里云CLI，请先安装: https://help.aliyun.com/document_detail/139508.html")
        sys.exit(1)

    # 获取凭证：命令行参数 > 环境变量 > CLI 配置文件
    access_key_id = args.ak
    access_key_secret = args.sk
    
    if not access_key_id or not access_key_secret:
        access_key_id, access_key_secret = get_credentials_from_env()
    
    if not access_key_id or not access_key_secret:
        access_key_id, access_key_secret = get_credentials_from_cli_config()
        if access_key_id and access_key_secret:
            print("使用已配置的阿里云 CLI 凭证")

    if not access_key_id or not access_key_secret:
        print(f"错误: 请提供 AK/SK，可通过以下方式之一：")
        print(f"  1. 环境变量: export {ENV_ACCESS_KEY_ID}=YOUR_AK && export {ENV_ACCESS_KEY_SECRET}=YOUR_SK")
        print(f"  2. 命令行参数: --ak YOUR_AK --sk YOUR_SK")
        print(f"  3. 配置阿里云 CLI: aliyun configure")
        sys.exit(1)

    # 配置 CLI 认证
    configure_aliyun_cli(access_key_id, access_key_secret, args.region)

    # 分发子命令
    if args.command == "create":
        cmd_create(args, args.region)
    elif args.command == "delete":
        cmd_delete(args, args.region)
    elif args.command == "get":
        cmd_get(args, args.region)
    elif args.command == "kubeconfig":
        cmd_kubeconfig(args, args.region)


if __name__ == "__main__":
    main()
