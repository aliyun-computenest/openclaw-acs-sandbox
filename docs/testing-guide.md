# OpenClaw Production Template 测试指南

## 目录

1. [测试体系概览](#1-测试体系概览)
2. [test_template_validation.py — 模版静态校验](#2-test_template_validationpy--模版静态校验)
3. [test_network_validation.py — 线上网络验证](#3-test_network_validationpy--线上网络验证)
4. [测试场景矩阵](#4-测试场景矩阵)
5. [已知限制与待办](#5-已知限制与待办)
6. [快速上手](#6-快速上手)

---

## 1. 测试体系概览

本项目包含两套互补的测试工具，覆盖从 YAML 静态分析到线上集群实测的完整验证链路。所有测试脚本位于 `tests/` 目录下：

| 测试文件 | 类型 | 依赖 | 覆盖范围 |
|---------|------|------|---------|
| `tests/openclaw_test.py` | **统一 CLI 入口** | Python 3 + aliyun CLI + kubectl | 一站式编排全部测试流程（推荐） |
| `tests/test_template_validation.py` | 离线静态校验 | 仅 Python 3 + PyYAML | 模版结构、引用完整性、CIDR 逻辑、安全组规则、依赖链 |
| `tests/test_network_validation.py` | 线上集群验证 | kubectl + aliyun CLI | VPC 拓扑、安全组实际规则、NAT 隔离、路由表、Pod 网络连通性 |

### 设计原则

- **动态适配**：网络验证不硬编码 CIDR，从 Stack 输出和 VPC DataSource 动态获取，支持任意 VPC 网段
- **分层测试**：静态校验 → 云资源校验 → Pod 级网络实测
- **严重度分级**：P0（安全关键）、P1（功能关键）、INFO（信息性）

---

## 2. test_template_validation.py — 模版静态校验

### 运行方式

```bash
python3 tests/test_template_validation.py
```

默认同时校验 `template-production.yaml`（当前版本）和 `template-production.yaml.bak`（旧版本），并输出对比报告。

### 测试项说明（共 19 项）

| # | 测试名称 | 说明 | 严重度 |
|---|---------|------|--------|
| 1 | YAML Structure | 检查 ROSTemplateFormatVersion、必要的顶层节 | ERROR |
| 2 | Parameter Validation | 检查必要参数存在、类型、Label、ZoneId 互斥关系 | ERROR |
| 3 | Reference Integrity | 所有 `Ref` 和 `Fn::GetAtt` 引用的参数/资源必须存在 | ERROR |
| 4 | Condition Integrity | 所有使用的 Condition 必须已定义，未使用的发出 WARN | ERROR/WARN |
| 5 | Dependency Chain | DependsOn 引用必须存在，不能有循环依赖 | ERROR |
| 6 | CIDR Validation | 验证默认 CIDR 的子网包含关系、无重叠、Service CIDR 无冲突 | ERROR |
| 7 | SecurityGroup Rules | 逐条验证出入方向规则：metadata拒绝、NAT/API Server 放行、DNS 放行（含 VPC CIDR DNS）、VPC/OpenClaw 拒绝、公网放行 | ERROR |
| 8 | TrafficPolicy Compliance | 检查 Poseidon Addon、GlobalTrafficPolicy、OpenClawTrafficPolicy 是否存在 | ERROR |
| 9 | NAT Gateway Setup | 验证 OpenClaw NAT 网关、EIP、EIP 绑定、3 条 SNAT 规则 | ERROR |
| 9b | Route Table Setup | 验证 OpenClawRouteTable、RouteEntry（ALIYUN::ECS::Route 类型、0.0.0.0/0 → NAT）、3 个 RouteTableAssociation | ERROR |
| 10 | Addon Installation Chain | 验证 ALB、Prometheus、SandboxController、SandboxManager 的依赖链 | ERROR/WARN |
| 11 | SandboxSet Validation | 验证 SandboxSet YAML 包含 ACS 注解 `security-group-ids`、`vswitch-ids`、安全配置 | ERROR |
| 12 | PrivateZone Setup | 验证 Zone、VpcBinder、CnameRecord 及 Condition | ERROR |
| 13 | ALB Config Job | 验证 ServiceAccount、ClusterRole、Binding、Job 及依赖 | ERROR |
| 14 | ExistingVPC CIDR Handling | 验证安全组使用 VpcDataSource 动态获取 CIDR（而非硬编码） | WARN |
| 14b | InternalClusterYaml & TestPod | 验证可选的内部 YAML 下发和测试 Pod 资源 | WARN |
| 14c | ALB VSwitch Condition Safety | 验证 UseCustomAlbVSwitchCondition 是否为复合条件（含 VpcOption 检查） | WARN |
| 15 | Outputs Completeness | 验证 10 个必要输出 | WARN |
| 16 | Metadata & ParameterGroups | 验证参数分组和隐藏参数 | WARN |
| 17 | Documentation Compliance | 对照架构文档检查：独立 VSwitch、安全组、NAT、TrafficPolicy | ERROR |

### ZoneId 互斥规则

当前规则（支持 2-AZ 退化场景）：
- `ZoneId1`：排除 `ZoneId2` 和 `ZoneId3`（Zone1 必须唯一）
- `ZoneId2`：仅排除 `ZoneId1`（允许与 Zone3 相同）
- `ZoneId3`：仅排除 `ZoneId1`（允许与 Zone2 相同）

这允许在只有 2 个可用区的地域中部署，Zone2 和 Zone3 选同一个 AZ。

### 安全组出方向规则检查清单

```
优先级  类型       检查项
  1     deny     metadata (100.100.100.200/32)
  2     allow    NAT upstream (443/53/80 → 默认NAT内网IP)
  2     allow    API Server (6443/9082 → API Server 内网IP)
  2     allow    阿里云DNS (53 → 100.100.2.136, 100.100.2.138)
  2     allow    VPC DNS (53 → VPC主网段，CoreDNS在业务VSwitch)
 10     deny     VPC主网段（动态获取，防横向移动）
 10     deny     OpenClaw辅助网段（防Sandbox间通信）
100     allow    公网兜底放行
```

---

## 3. test_network_validation.py — 线上网络验证

### 运行方式

```bash
# 方式1：通过 Stack Name（推荐，自动获取所有资源 ID）
python3 tests/test_network_validation.py --stack-name test-alb-vsw-01 --region cn-hangzhou

# 方式2：指定 Cluster ID 和 SecurityGroup ID
python3 tests/test_network_validation.py --cluster-id <id> --region cn-hangzhou --sg-id <sg-id>

# 方式3：仅 kubectl 测试（跳过云 API 检查）
python3 tests/test_network_validation.py --kubectl-only

# 启用 Poseidon/TrafficPolicy 测试（默认跳过）
python3 tests/test_network_validation.py --stack-name <name> --region cn-hangzhou --test-poseidon
```

### 前置条件

- `kubectl` 已配置正确的 kubeconfig 并可连接集群
- `aliyun` CLI 已配置有效凭证（非 `--kubectl-only` 模式）
- 集群中存在 Running 状态的 `app=openclaw` Pod

### 测试项说明（共 11 大类）

| # | 测试类别 | 检查内容 | 动态适配 |
|---|---------|---------|---------|
| 0 | Stack Info | 从 ROS 加载 Stack 输出和参数，获取资源 ID | - |
| 1 | Kubectl Connectivity | 验证 kubectl 可连接集群 | - |
| 2 | VPC & VSwitch Topology | VPC 主/辅 CIDR、6+ VSwitch、AZ 分布 | 根据实际 VPC CIDR 动态分类 VSwitch |
| 3 | SecurityGroup Rules | 入方向规则、出方向规则逐条验证（metadata/NAT/DNS/VPC deny） | 从 VPC DataSource 动态获取 CIDR |
| 4 | NAT Gateway Isolation | 双 NAT（默认 + OpenClaw）、Enhanced 类型、EIP 绑定、3 条 SNAT | 对比 Stack 输出 EIP |
| 4b | Route Table Isolation | 自定义路由表、默认路由 → OpenClaw NAT、3 个 VSwitch 关联 | 对比 Stack 输出 NAT ID |
| 5 | Core K8s Resources | Namespace、SandboxSet、sandbox-manager、TLS Secret、Multi-AZ nodes | - |
| 6 | Pod Annotations | `security-group-ids`、`vswitch-ids`、实际 ENI 绑定验证 | 对比 Stack 输出 SG ID |
| 7 | Network Connectivity | 公网访问 / DNS / metadata 拒绝 / VPC 内网拒绝 / 横向隔离 / NAT EIP / VSwitch / ENI | 动态 CIDR |
| 8 | Security Hardening | automountServiceAccountToken / enableServiceLinks / SA token volume | - |
| 9 | ALB & Ingress | Ingress 资源、ALB 443 端口、DNS Name | - |
| 10 | PrivateZone DNS | 从 Sandbox Pod 内解析 PrivateZone 域名、resolv.conf | - |
| 11 | TrafficPolicy | Poseidon CRD、GlobalTrafficPolicy、TrafficPolicy（默认跳过） | - |

### 网络连通性测试详情（第 7 项）

从 Sandbox Pod 内部执行的测试：

| 子项 | 命令 | 预期结果 | 原理 |
|-----|------|---------|------|
| 公网访问 | `curl https://www.alibaba.com` | HTTP 200 | OpenClaw NAT SNAT + 安全组 P100 放行 |
| DNS 解析 | `getent hosts www.alibaba.com` | 成功解析 | 安全组 P2 放行 DNS 53 到 VPC CIDR + 阿里云 DNS |
| Metadata 拒绝 | `curl http://100.100.100.200` | 超时/403 | 安全组 P1 drop 100.100.100.200 |
| VPC 内网拒绝 | `curl http://<vpc_first_ip>` | 超时 | 安全组 P10 drop VPC 主网段 |
| sandbox-manager 隔离 | `curl http://<sm_ip>:8080` | 超时 | 安全组 P10 drop（TrafficPolicy 就绪后更精确） |
| NAT EIP 验证 | `curl ifconfig.me` | OpenClaw NAT EIP | 自定义路由表 → OpenClaw NAT → SNAT |
| VSwitch 检查 | 读取 Pod annotation | 在 OpenClaw CIDR 范围 | `vswitch-ids` 注解生效 |
| ENI 安全组 | 查询 ENI 接口 | OpenClaw SG | `security-group-ids` 注解生效 |

---

## 4. 测试场景矩阵

以下是需要覆盖的部署场景及已测试状态：

| 场景 | VpcOption | EnableCustomAlbVSwitch | 状态 |
|-----|-----------|----------------------|------|
| NewVPC + 默认 ALB VSwitch | NewVPC | false | **已测试通过** |
| ExistingVPC + 默认 ALB VSwitch | ExistingVPC | false | **已测试通过** |
| ExistingVPC + 自定义 ALB VSwitch | ExistingVPC | true | 待测试 |
| NewVPC + EnableCustomAlbVSwitch=true | NewVPC | true | 被复合条件安全阻止（等效 false） |
| 2-AZ 退化（Zone2 = Zone3） | 任意 | 任意 | 待测试 |
| EnablePrivateZone=false | 任意 | 任意 | 待测试 |
| EnablePublicIp=false（内网 ALB） | 任意 | 任意 | 待测试 |
| InternalClusterYaml 非空 | 任意 | 任意 | 待测试 |

### 跨地域测试

| 地域 | 状态 | 备注 |
|------|------|------|
| cn-hangzhou | **已测试** | 主测试地域 |
| cn-beijing | 待测试 | 验证地域参数自动适配 |
| cn-shanghai | 待测试 | - |
| cn-hongkong | 待测试 | 海外地域 |
| ap-southeast-1 | 待测试 | 国际地域，镜像源切换 |

---

## 5. 已知限制与待办

### 已知延后项（P0 级，等 ACS 组件发布）

| 项目 | 说明 | 阻塞原因 |
|------|------|---------|
| PoseidonAddon | 提供 TrafficPolicy/GlobalTrafficPolicy CRD | ACS 尚未发布 Poseidon 组件 |
| GlobalTrafficPolicyApplication | 全局拒绝 OpenClaw CIDR 到其他 Pod 的入向流量 | 依赖 Poseidon |
| OpenClawTrafficPolicyApplication | OpenClaw Pod 精细化出入向控制 | 依赖 Poseidon |
| SandboxSet DependsOn TrafficPolicy | SandboxSet 应在 TrafficPolicy 就绪后才创建 | 依赖 Poseidon |

### 测试工具当前限制

1. **`tests/test_network_validation.py` 不支持同时测试多集群**：每次运行依赖当前 kubeconfig，测试多集群需手动切换
2. **安全组规则匹配基于精确 CIDR 字符串**：如果安全组使用了 `Fn::Jq` 计算出的 CIDR 与预期格式略有不同（如 `172.20.0.0/16` vs `172.20.0.0/16`），仍能匹配
3. **`tests/test_template_validation.py` 不验证 `Fn::Sub` 模板字符串的语法正确性**：YAML 中内嵌的 K8s manifest 只做关键字包含检查

---

## 6. 快速上手

### 一键完整测试（推荐）

使用统一 CLI 入口，自动完成环境检查、公网保护解除、安全组配置、网络验证全流程：

```bash
# 完整测试
python3 tests/openclaw_test.py --stack-name my-test --region cn-hangzhou \
    --accesskey LTAI*** --accesskey-secret ****

# 含 Sandbox 端到端
python3 tests/openclaw_test.py --stack-name my-test --region cn-hangzhou \
    --accesskey LTAI*** --accesskey-secret **** --sandbox-test

# 仅静态模版校验（无需集群）
python3 tests/openclaw_test.py --template-only
```

### 分步手动测试（CLI）

```bash
# 1. 静态模版校验
python3 tests/test_template_validation.py

# 2. 部署 Stack
python3 ros_stack_manager.py create \
  --stack-name my-test \
  --template template-production.yaml \
  --parameters parameters-production-hangzhou.yaml \
  --region cn-hangzhou

# 3. 获取 kubeconfig
python3 ros_stack_manager.py kubeconfig \
  --cluster-id <CLUSTER_ID> \
  --region cn-hangzhou

# 4. （阿里内网测试）关闭云防火墙
aliyun cloudfw PutDisableFwSwitch \
  --IpaddrList.1 <eip1> --IpaddrList.2 <eip2> \
  --endpoint cloudfw.aliyuncs.com

# 5. （阿里内网测试）将 NAT EIP 加入 ALB 安全组
aliyun ecs AuthorizeSecurityGroup \
  --RegionId cn-hangzhou \
  --SecurityGroupId <ALB_SG_ID> \
  --IpProtocol tcp --PortRange 1/65535 \
  --SourceCidrIp <NAT_EIP>/32 --Priority 1

# 6. 运行网络验证
python3 tests/test_network_validation.py \
  --stack-name my-test \
  --region cn-hangzhou
```

---

## 7. 控制台手动验证流程

如果你不方便使用脚本，或者需要在阿里云控制台上一步步确认，按以下清单逐项验证。

> **前提**：ROS Stack 已创建完成（状态 `CREATE_COMPLETE`）。
> 先到 [ROS 控制台](https://ros.console.aliyun.com/) → 选择对应地域 → 点击你的 Stack → 「输出」Tab，记录以下关键值：
>
> | 输出项 | 示例值 | 用途 |
> |--------|--------|------|
> | `ClusterId` | `c236d0aaa...` | 定位集群 |
> | `VpcId` | `vpc-2ze7k...` | 定位 VPC |
> | `OpenClawSecurityGroupId` | `sg-2zec9...` | OpenClaw 专用安全组 |
> | `OpenClawNatGatewayId` | `ngw-2zec7...` | OpenClaw 独立 NAT |
> | `OpenClawNatEipAddress` | `8.131.108.212` | OpenClaw 出公网 EIP |
> | `DefaultNatGatewayIp` | `192.168.0.110` | 集群默认 NAT 内网 IP |
> | `ApiServerIntranetIp` | `192.168.0.109` | API Server 内网 IP |
> | `ALB_DNS_Name` | `alb-xxx.cn-beijing.alb.aliyuncsslb.com` | ALB 入口 |
> | `E2B_API_KEY` | `oc_xxx` | E2B API Key |
> | `E2B_DOMAIN` | `agent-vpc.infra` | E2B 域名 |

---

### Step 1 — VPC 拓扑验证

**控制台路径**: [VPC 控制台](https://vpc.console.aliyun.com/) → 选地域 → 点击 VpcId

| 检查项 | 预期 | 如何验证 |
|--------|------|---------|
| 主网段 | `192.168.0.0/16`（或自定义） | VPC 详情页 → 「IPv4 网段」 |
| 辅助网段 | `10.8.0.0/16`（OpenClaw 专用） | VPC 详情页 → 「辅助 IPv4 网段」 |
| VSwitch 总数 | ≥ 6 | 左侧菜单「交换机」→ 筛选此 VPC |
| 业务 VSwitch | 3 个，网段在主网段内（如 `192.168.0.0/24`、`192.168.1.0/24`、`192.168.2.0/24`），分布在不同可用区 | 按网段排序确认 |
| OpenClaw VSwitch | 3 个，网段在辅助网段内（如 `10.8.0.0/18`、`10.8.64.0/18`、`10.8.128.0/18`），名称包含 `openclaw` | 按名称筛选 `openclaw` |
| 可用区覆盖 | 业务和 OpenClaw VSwitch 各覆盖 ≥ 2 个可用区 | 查看每个 VSwitch 的「可用区」列 |

---

### Step 2 — 安全组规则验证

**控制台路径**: [ECS 控制台](https://ecs.console.aliyun.com/) → 网络与安全 → 安全组 → 找到 `OpenClawSecurityGroupId`

#### 入方向规则（3 条）

| 优先级 | 策略 | 协议 | 端口 | 源地址 | 用途 |
|--------|------|------|------|--------|------|
| 1 | 允许 | 全部 | -1/-1 | `192.168.0.0/24` | 允许业务 VSwitch1 访问（gateway/manager） |
| 1 | 允许 | 全部 | -1/-1 | `192.168.1.0/24` | 允许业务 VSwitch2 访问 |
| 1 | 允许 | 全部 | -1/-1 | `192.168.2.0/24` | 允许业务 VSwitch3 访问 |

#### 出方向规则（16 条，按优先级排列）

| 优先级 | 策略 | 协议 | 端口 | 目的地址 | 用途 |
|--------|------|------|------|---------|------|
| **1** | **拒绝** | 全部 | -1/-1 | `100.100.100.200/32` | 拒绝 metadata 服务 |
| 2 | 允许 | TCP | 443 | `{DefaultNatGatewayIp}/32` | HTTPS 到上游 NAT |
| 2 | 允许 | TCP | 80 | `{DefaultNatGatewayIp}/32` | HTTP 到上游 NAT |
| 2 | 允许 | TCP | 53 | `{DefaultNatGatewayIp}/32` | DNS-TCP 到上游 NAT |
| 2 | 允许 | UDP | 53 | `{DefaultNatGatewayIp}/32` | DNS-UDP 到上游 NAT |
| 2 | 允许 | TCP | 6443 | `{ApiServerIntranetIp}/32` | K8s API Server |
| 2 | 允许 | TCP | 9082 | `{ApiServerIntranetIp}/32` | Poseidon |
| 2 | 允许 | TCP | 53 | `100.100.2.136/32` | 阿里云内网 DNS |
| 2 | 允许 | UDP | 53 | `100.100.2.136/32` | 阿里云内网 DNS-UDP |
| 2 | 允许 | TCP | 53 | `100.100.2.138/32` | 阿里云内网 DNS |
| 2 | 允许 | UDP | 53 | `100.100.2.138/32` | 阿里云内网 DNS-UDP |
| 2 | 允许 | TCP | 53 | VPC 主网段 | DNS 到 CoreDNS（业务 VSwitch） |
| 2 | 允许 | UDP | 53 | VPC 主网段 | DNS 到 CoreDNS |
| **10** | **拒绝** | 全部 | -1/-1 | VPC 主网段 | 拒绝横向访问 VPC 内网 |
| **10** | **拒绝** | 全部 | -1/-1 | `10.8.0.0/16` | 拒绝 Sandbox 间横向通信 |
| 100 | 允许 | 全部 | -1/-1 | `0.0.0.0/0` | 兜底放行公网 |

**关键验证点**：
- 优先级 1 的 metadata 拒绝 **必须** 存在且在最高优先级
- 优先级 10 的两条 deny 规则覆盖了 VPC 主网段 和 OpenClaw 辅助网段
- 优先级 2 的 allow 规则只放行了特定 IP + 端口
- 优先级 100 的公网 allow 因低于 deny 规则，不会影响内网隔离

---

### Step 3 — NAT 网关隔离验证

**控制台路径**: [NAT 控制台](https://vpc.console.aliyun.com/nat) → 选地域

| 检查项 | 预期 | 如何验证 |
|--------|------|---------|
| NAT 网关数量 | ≥ 2 个（集群默认 + OpenClaw） | 筛选对应 VPC |
| OpenClaw NAT 名称 | 包含 `openclaw-nat-` | 名称列 |
| OpenClaw NAT 类型 | `增强型` | 规格列 |
| OpenClaw NAT 描述 | `OpenClaw Sandbox Pod 独立 NAT 网关，出公网流量隔离` | 描述列 |
| EIP 绑定 | 绑定了 `OpenClawNatEipAddress` 对应的 EIP | 点击 NAT → 弹性公网 IP |
| SNAT 规则 | 3 条，分别对应 3 个 OpenClaw VSwitch | 点击 NAT → SNAT 管理 |

逐条验证 SNAT 规则：

| SNAT 名称 | 源 VSwitch | 公网 IP | 状态 |
|-----------|-----------|---------|------|
| `openclaw-snat-vsw1` | OpenClaw VSwitch1 | `OpenClawNatEipAddress` | Available |
| `openclaw-snat-vsw2` | OpenClaw VSwitch2 | 同上 | Available |
| `openclaw-snat-vsw3` | OpenClaw VSwitch3 | 同上 | Available |

---

### Step 4 — 路由表隔离验证

**控制台路径**: [VPC 控制台](https://vpc.console.aliyun.com/) → 路由表

| 检查项 | 预期 | 如何验证 |
|--------|------|---------|
| 自定义路由表 | 存在 1 个，名称包含 `openclaw-rt-` | 路由表列表页，类型筛选「自定义」 |
| 关联 VSwitch | 3 个 OpenClaw VSwitch | 点击路由表 → 「已绑定交换机」Tab |
| 默认路由 | `0.0.0.0/0` → 下一跳类型 `NAT 网关`，下一跳为 OpenClaw NAT ID | 「路由条目」Tab |

**核心逻辑**：OpenClaw VSwitch 关联了独立路由表 → 默认路由指向 OpenClaw NAT → 出公网流量走 OpenClaw 专用 EIP，与集群默认 NAT 完全隔离。

---

### Step 5 — 集群资源验证

**控制台路径**: [ACK/ACS 控制台](https://cs.console.aliyun.com/) → 选地域 → 点击集群

#### 5.1 节点

| 检查项 | 预期 |
|--------|------|
| 节点类型 | `virtual-kubelet`（ACS 无真实节点） |
| 节点数量 | ≥ 2 个（多可用区） |
| 可用区 | 覆盖 ≥ 2 个 AZ |

#### 5.2 命名空间 & 工作负载

通过控制台或 kubectl 确认：

```bash
# sandbox-system 命名空间
kubectl get ns sandbox-system

# SandboxSet（自定义资源）
kubectl get sandboxset openclaw -n default

# sandbox-manager（3 副本）
kubectl get pods -n sandbox-system -l app.kubernetes.io/name=ack-sandbox-manager

# TLS 证书
kubectl get secret sandbox-manager-tls -n sandbox-system
```

#### 5.3 Sandbox Pod 注解验证

```bash
# 取一个运行中的 openclaw Pod
POD=$(kubectl get pods -n default -l app=openclaw --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')

# 检查安全组注解（应为 OpenClawSecurityGroupId）
kubectl get pod $POD -n default -o jsonpath='{.metadata.annotations.network\.alibabacloud\.com/security-group-ids}'

# 检查 VSwitch 注解（应为 3 个 OpenClaw VSwitch）
kubectl get pod $POD -n default -o jsonpath='{.metadata.annotations.network\.alibabacloud\.com/vswitch-ids}'

# 检查 Pod IP（应在 10.8.0.0/16 范围内）
kubectl get pod $POD -n default -o jsonpath='{.status.podIP}'
```

---

### Step 6 — 从 Sandbox Pod 内测试网络隔离

这是最核心的验证步骤，在 Sandbox Pod 内部实际测试网络策略是否生效。

```bash
# 找到运行中的 openclaw Pod
POD=$(kubectl get pods -n default -l app=openclaw --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
```

#### 6.1 公网访问（预期：成功）

```bash
kubectl exec $POD -n default -c openclaw -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 https://www.alibaba.com
# 预期输出: 200
```

#### 6.2 DNS 解析（预期：成功）

```bash
kubectl exec $POD -n default -c openclaw -- getent hosts www.alibaba.com
# 预期输出: 解析出 IP 地址
```

#### 6.3 metadata 拒绝（预期：超时或 403）

```bash
kubectl exec $POD -n default -c openclaw -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://100.100.100.200/latest/meta-data/
# 预期输出: 000（超时）或 403（ACS 平台拦截）
# ❌ 如果输出 200，说明 metadata 安全规则未生效！
```

#### 6.4 VPC 内网横向移动拒绝（预期：超时）

```bash
kubectl exec $POD -n default -c openclaw -- curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 http://192.168.0.1
# 预期输出: 000（超时 = 被安全组拒绝）
# ❌ 如果输出 200/其他，说明 VPC deny 规则未生效！
```

#### 6.5 出口 IP 验证（预期：OpenClaw NAT EIP）

```bash
kubectl exec $POD -n default -c openclaw -- curl -s --connect-timeout 5 https://httpbin.org/ip
# 预期输出: {"origin": "8.131.108.212"}  ← 应为 OpenClawNatEipAddress
# ❌ 如果返回集群默认 NAT EIP，说明路由表或 SNAT 未正确配置！
```

#### 6.6 PrivateZone DNS 解析（预期：解析到 ALB）

```bash
kubectl exec $POD -n default -c openclaw -- getent hosts test.agent-vpc.infra
# 预期输出: ALB 的 IP 地址 + CNAME
# ❌ 如果无法解析，检查 PrivateZone 配置和 VPC 绑定
```

#### 6.7 安全加固检查

```bash
# automountServiceAccountToken 应为 false
kubectl get pod $POD -n default -o jsonpath='{.spec.automountServiceAccountToken}'
# 预期: false

# enableServiceLinks 应为 false
kubectl get pod $POD -n default -o jsonpath='{.spec.enableServiceLinks}'
# 预期: false

# 不应有 kube-api-access 卷
kubectl get pod $POD -n default -o jsonpath='{.spec.volumes[*].name}'
# 预期: 只有 envd-volume，没有 kube-api-access-xxx
```

---

### Step 7 — ALB & Ingress 验证

**控制台路径**: [SLB/ALB 控制台](https://slb.console.aliyun.com/) → 应用型负载均衡

| 检查项 | 预期 | 如何验证 |
|--------|------|---------|
| ALB 实例存在 | DNS Name 匹配 `ALB_DNS_Name` 输出 | 实例列表 |
| 监听端口 | 80 + 443 | 点击 ALB → 「监听」Tab |
| 443 证书 | 已配置 TLS 证书 | 监听详情 |

Ingress 验证：

```bash
kubectl get ingress -n sandbox-system
# 预期: sandbox-manager，hosts 为 *.agent-vpc.infra 和 agent-vpc.infra
```

---

### Step 8 — PrivateZone 验证

**控制台路径**: [PrivateZone 控制台](https://dns.console.aliyun.com/#/privateZone/list)

| 检查项 | 预期 |
|--------|------|
| Zone 名称 | `E2B_DOMAIN`（如 `agent-vpc.infra`） |
| 关联 VPC | 已绑定部署的 VPC |
| CNAME 记录 | `*.agent-vpc.infra` → ALB DNS Name |

---

### 验证结果汇总清单

完成以上步骤后，对照以下清单确认全部通过：

```
□ Step 1: VPC 主网段 + 辅助网段正确，6 个 VSwitch 跨 ≥2 AZ
□ Step 2: 安全组 16 条出方向 + 3 条入方向规则完整且优先级正确
□ Step 3: 独立 NAT 网关 + EIP + 3 条 SNAT 规则
□ Step 4: 自定义路由表关联 3 个 OpenClaw VSwitch，默认路由 → OpenClaw NAT
□ Step 5: 集群资源就绪，Pod 注解包含正确的安全组和 VSwitch
□ Step 6.1: 公网访问 → HTTP 200 ✓
□ Step 6.2: DNS 解析 → 成功 ✓
□ Step 6.3: metadata → 超时或 403 ✓
□ Step 6.4: VPC 内网 → 超时 ✓
□ Step 6.5: 出口 IP → OpenClaw NAT EIP ✓
□ Step 6.6: PrivateZone → 解析成功 ✓
□ Step 6.7: 安全加固 → automountSA=false, enableServiceLinks=false ✓
□ Step 7: ALB 监听 443，Ingress 配置正确
□ Step 8: PrivateZone 已关联 VPC，CNAME 指向 ALB

⚠ 待 Poseidon 发布后追加:
□ TrafficPolicy: 全局拒绝 OpenClaw → 其他 Pod 的入向流量
□ TrafficPolicy: OpenClaw Pod 只允许 gateway/manager 入向
```
