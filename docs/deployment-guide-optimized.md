# OpenClaw 企业版部署指南

> 基于 ACS Agent Sandbox 构建企业级 AI Agent 应用

## 概述

OpenClaw 是一款开源的 AI 编程助手，支持多平台运行。本服务基于阿里云 ACS（容器计算服务）和 OpenKruise Agents 框架，提供企业级的一键部署方案。

### 核心特性

- **秒级沙箱启动**：通过 SandboxSet 预热池实现亚秒级沙箱交付
- **会话状态保持**：支持沙箱休眠与唤醒，保留内存状态
- **持久化存储**：集成 NAS 文件存储，数据跨会话持久化
- **自动公网访问**：每个沙箱自动分配独立 EIP 或 LoadBalancer
- **E2B 协议兼容**：支持原生 E2B SDK，无缝迁移现有应用

### 部署方式对比

| 部署方式 | 难度 | 时间 | 适用场景 |
|---------|------|------|---------|
| **计算巢控制台** | ⭐ 简单 | 5-10分钟 | 快速体验、测试环境 |
| **ROS 一键部署** | ⭐⭐ 中等 | 10-15分钟 | 生产环境、企业部署 |
| **手动部署** | ⭐⭐⭐ 复杂 | 30-60分钟 | 定制化需求、学习研究 |

## 方式一：计算巢控制台部署（推荐新手）

### 前提准备

#### 1. 准备域名

E2B 协议需要一个域名（E2B_DOMAIN）来指定后端服务。

- **测试环境**：可使用测试域名，如 `agent-vpc.infra`
- **生产环境**：
  - 如果您还没有域名，参考 [域名注册快速入门](https://help.aliyun.com/document_detail/35789.html)
  - 如果部署在中国内地，需要进行 [域名备案](https://beian.aliyun.com/)

#### 2. 获取 TLS 证书

E2B 客户端通过 HTTPS 请求后端，需要申请通配符证书。

**测试环境 - 自签名证书：**

```bash
# 下载证书生成脚本
curl -O https://raw.githubusercontent.com/openclaw/openclaw/main/scripts/generate-certificates.sh
chmod +x generate-certificates.sh

# 生成证书
./generate-certificates.sh --domain agent-vpc.infra --days 730
```

生成的文件：
- `fullchain.pem`：服务器证书公钥
- `privkey.pem`：服务器证书私钥

**生产环境 - Let's Encrypt 免费证书：**

```bash
# 安装 certbot
brew install certbot  # macOS
# 或 snap install certbot  # Linux

# 申请通配符证书
sudo certbot certonly \
  --manual \
  --preferred-challenges=dns \
  --email your-email@example.com \
  --server https://acme-v02.api.letsencrypt.org/directory \
  --agree-tos \
  -d "*.your.domain.cn"

# 导出证书
sudo cp /etc/letsencrypt/live/your.domain/fullchain.pem ./fullchain.pem
sudo cp /etc/letsencrypt/live/your.domain/privkey.pem ./privkey.pem
```

**生产环境 - 购买正式证书：**

推荐 [购买正式证书](https://help.aliyun.com/document_detail/28542.html)，安全性更高。

#### 3. 获取百炼 API Key

登录 [百炼控制台](https://bailian.console.aliyun.com/) 创建 API Key，用于 AI 模型调用。

### 部署步骤

1. **访问计算巢服务**
   
   打开 [计算巢服务部署链接](https://computenest.console.aliyun.com/)

2. **填写部署参数**

   基本配置：
   - **地域**：选择就近地域（如 cn-hangzhou、cn-beijing）
   - **可用区**：选择两个不同的可用区（用于高可用）
   - **VPC 配置**：选择新建或使用已有 VPC

   E2B 配置：
   - **E2B 域名**：填写前提准备阶段的域名
   - **TLS 证书**：上传 `fullchain.pem` 文件
   - **TLS 证书私钥**：上传 `privkey.pem` 文件

   资源配置：
   - **sandbox-manager CPU**：默认 2 核，可按需调整
   - **sandbox-manager 内存**：默认 4Gi，可按需调整

3. **确认部署**

   点击「确认订单」开始部署，约需 5-10 分钟完成。

4. **获取访问信息**

   部署成功后，在服务实例详情页可查看：
   - **E2B_API_KEY**：访问 E2B API 的密钥
   - **E2B_DOMAIN**：E2B 域名
   - **OpenClawAccessUrl**：OpenClaw 访问地址

### 配置域名解析

#### 本地测试（Hosts 方式）

```bash
# 1. 获取 ALB 访问端点
# 在服务实例详情页找到 ACS 控制台链接
# 查看 sandbox-manager 的网关，获取 ALB 端点

# 2. 获取 ALB 公网 IP
ping alb-xxxxxx.cn-hangzhou.alb.aliyuncs.com

# 3. 配置本地 hosts
echo "ALB_PUBLIC_IP E2B_DOMAIN" >> /etc/hosts
# 示例：
# 47.xxx.xxx.xxx api.agent-vpc.infra
```

#### 生产环境（DNS 解析）

```bash
# 将域名以 A 记录或 CNAME 记录解析到 ALB 端点
# 例如：api.your.domain.cn CNAME alb-xxxxxx.cn-hangzhou.alb.aliyuncs.com
```

## 方式二：ROS 模板一键部署（推荐生产环境）

### 前提准备

与计算巢控制台部署相同，需要准备：
1. 域名
2. TLS 证书
3. 百炼 API Key
4. OpenClaw 访问 Token

### 配置镜像缓存（推荐）

镜像缓存可以显著加速 ACS Pod 启动，将镜像拉取时间从分钟级降低到秒级。

> **注意**：镜像缓存功能目前在白名单邀测阶段，需要 [提交工单](https://workorder.console.aliyun.com/) 申请开通。

**创建镜像缓存：**

1. 登录 [容器计算服务控制台](https://acs.console.aliyun.com/)
2. 在左侧导航栏选择「镜像缓存」
3. 点击「创建镜像缓存」，配置：
   - **镜像缓存名**：`openclaw-image-cache`
   - **镜像**：`registry.cn-hangzhou.aliyuncs.com/acs-samples/clawdbot:2026.1.24.3`
   - **网络连通性**：选择公网方式或 VPC 内网方式
4. 等待镜像缓存状态变为「制作完成」

**计费说明：**
- 每个地域免费 20 个镜像缓存
- 超出部分：0.18 元/GiB/月
- 加速使用费：0.00231 元/GiB/小时

**支持地域：**
华北2（北京）、华东2（上海）、华东1（杭州）、华北6（乌兰察布）、华南1（深圳）、中国香港、新加坡

### 准备参数文件

创建 `parameters.yaml` 文件：

```yaml
# 地域和可用区
ZoneId1: cn-beijing-c
ZoneId2: cn-beijing-d

# OpenClaw 配置
OpenClawReplicas: 1  # 预热副本数
OpenClawImage: registry.cn-hangzhou.aliyuncs.com/acs-samples/clawdbot:2026.1.24.3
BaiLianApiKey: '{"ApiKeyValue": "sk-your-api-key", "WorkspaceId": "ws_xxx"}'
OpenClawGatewayToken: your-access-token  # 自定义访问令牌
AdminApiKey: your-admin-api-key  # 管理员 API 密钥

# E2B 域名配置
E2BDomainAddress: your.domain.cn
TLSCertificate: |
  -----BEGIN CERTIFICATE-----
  ... your certificate content ...
  -----END CERTIFICATE-----
TLSPrivateKey: |
  -----BEGIN PRIVATE KEY-----
  ... your private key content ...
  -----END PRIVATE KEY-----
```

### 执行部署

```bash
# 1. 验证模板
aliyun ros ValidateTemplate --TemplateBody "$(cat template.yaml)" --RegionId cn-beijing

# 2. 创建 Stack
aliyun ros CreateStack \
  --RegionId cn-beijing \
  --StackName openclaw-prod \
  --TemplateBody "$(cat template.yaml)" \
  --Parameters "$(cat parameters.yaml)"

# 3. 查询部署状态
aliyun ros GetStack --RegionId cn-beijing --StackId <stack-id>
```

### 获取部署输出

```bash
# 获取 Stack 输出
aliyun ros GetStack --RegionId cn-beijing --StackId <stack-id> | jq '.Outputs'
```

输出包含：
- **OpenClawAccessUrl**：OpenClaw 访问地址（`http://<EIP>:18789/?token=<token>`）
- **E2BDomain**：E2B 域名
- **E2BApiKey**：E2B API 密钥
- **NASFileSystemId**：NAS 文件系统 ID
- **NASMountTargetDomain**：NAS 挂载点地址

## 方式三：手动部署（高级用户）

### 前提条件

1. **创建 ACK/ACS 集群**
   
   参考 [创建 ACS 集群](https://help.aliyun.com/document_detail/2584271.html)

2. **安装 ACS Agent Sandbox 组件**

   ```bash
   # 安装 OpenKruise
   helm repo add kruise https://openkruise.github.io/charts/
   helm install kruise kruise/kruise
   
   # 安装 ACS Agent Sandbox 组件
   helm repo add ack-sandbox https://acs-ecp.oss-cn-hangzhou.aliyuncs.com/charts/
   helm install sandbox-manager ack-sandbox/sandbox-manager -n sandbox-system --create-namespace
   ```

### 方案一：通过 Sandbox CR 直接创建

创建 `sandbox.yaml`：

```yaml
apiVersion: agents.kruise.io/v1alpha1
kind: Sandbox
metadata:
  name: openclaw
  namespace: default
spec:
  template:
    metadata:
      labels:
        alibabacloud.com/acs: "true"
        app: openclaw
      annotations:
        network.alibabacloud.com/pod-with-eip: "true"
        network.alibabacloud.com/eip-bandwidth: "5"
    spec:
      initContainers:
        - name: init
          image: registry-cn-hangzhou.ack.aliyuncs.com/acs/agent-runtime:v0.0.2
          imagePullPolicy: IfNotPresent
          command: ["sh", "/workspace/entrypoint_inner.sh"]
          volumeMounts:
            - name: envd-volume
              mountPath: /mnt/envd
          env:
            - name: ENVD_DIR
              value: /mnt/envd
            - name: __IGNORE_RESOURCE__
              value: "true"
      containers:
        - name: openclaw
          image: registry.cn-hangzhou.aliyuncs.com/acs-samples/clawdbot:2026.1.24.3
          imagePullPolicy: IfNotPresent
          securityContext:
            readOnlyRootFilesystem: false
            runAsUser: 0
            runAsGroup: 0
          resources:
            requests:
              cpu: 4
              memory: 8Gi
            limits:
              cpu: 4
              memory: 8Gi
          env:
            - name: ENVD_DIR
              value: /mnt/envd
            - name: DASHSCOPE_API_KEY
              value: sk-xxxxxxxxxxxxxxxxx  # 替换为真实 API Key
            - name: GATEWAY_TOKEN
              value: clawdbot-mode-123456  # 替换为访问 Token
          volumeMounts:
            - name: envd-volume
              mountPath: /mnt/envd
          startupProbe:
            tcpSocket:
              port: 18789
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 30
          lifecycle:
            postStart:
              exec:
                command:
                  - /bin/bash
                  - -c
                  - /mnt/envd/envd-run.sh
      volumes:
        - emptyDir: {}
          name: envd-volume
```

应用配置：

```bash
kubectl apply -f sandbox.yaml
```

### 方案二：通过 SandboxSet 创建预热池（推荐）

创建 `sandboxset.yaml`：

```yaml
apiVersion: agents.kruise.io/v1alpha1
kind: SandboxSet
metadata:
  name: openclaw
  namespace: default
  annotations:
    e2b.agents.kruise.io/should-init-envd: "true"
  labels:
    app: openclaw
spec:
  replicas: 1  # 预热副本数
  template:
    metadata:
      labels:
        alibabacloud.com/acs: "true"
        app: openclaw
      annotations:
        network.alibabacloud.com/pod-with-eip: "true"
        network.alibabacloud.com/eip-bandwidth: "5"
    spec:
      initContainers:
        - name: init
          image: registry-cn-hangzhou.ack.aliyuncs.com/acs/agent-runtime:v0.0.2
          imagePullPolicy: IfNotPresent
          command: ["sh", "/workspace/entrypoint_inner.sh"]
          volumeMounts:
            - name: envd-volume
              mountPath: /mnt/envd
          env:
            - name: ENVD_DIR
              value: /mnt/envd
            - name: __IGNORE_RESOURCE__
              value: "true"
          restartPolicy: Always
      containers:
        - name: openclaw
          image: registry.cn-hangzhou.aliyuncs.com/acs-samples/clawdbot:2026.1.24.3
          imagePullPolicy: IfNotPresent
          securityContext:
            readOnlyRootFilesystem: false
            runAsUser: 0
            runAsGroup: 0
          resources:
            requests:
              cpu: 4
              memory: 8Gi
            limits:
              cpu: 4
              memory: 8Gi
          env:
            - name: ENVD_DIR
              value: /mnt/envd
            - name: DASHSCOPE_API_KEY
              value: sk-xxxxxxxxxxxxxxxxx
            - name: GATEWAY_TOKEN
              value: clawdbot-mode-123456
          volumeMounts:
            - name: envd-volume
              mountPath: /mnt/envd
          startupProbe:
            tcpSocket:
              port: 18789
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 30
          lifecycle:
            postStart:
              exec:
                command:
                  - /bin/bash
                  - -c
                  - /mnt/envd/envd-run.sh
      volumes:
        - emptyDir: {}
          name: envd-volume
```

应用配置：

```bash
kubectl apply -f sandboxset.yaml
```

查看状态：

```bash
# 查看 SandboxSet 状态
kubectl get sandboxset -n default

# 查看沙箱状态
kubectl get sandbox -n default

# 查看 Pod 状态
kubectl get pods -l app=openclaw
```

### 从预热池获取沙箱

创建 `sandboxclaim.yaml`：

```yaml
apiVersion: agents.kruise.io/v1alpha1
kind: SandboxClaim
metadata:
  name: openclaw-claim
spec:
  templateName: openclaw  # SandboxSet 名称
  replicas: 1
  claimTimeout: 1m
  ttlAfterCompleted: 5m
```

应用配置：

```bash
kubectl apply -f sandboxclaim.yaml

# 查看 claim 状态
kubectl get sandboxclaim

# 查看已 claim 的沙箱
kubectl get sandbox -l agents.kruise.io/claim-name=openclaw-claim
```

## 使用 OpenClaw

### 通过 EIP 访问

查看沙箱分配的 EIP：

```bash
kubectl get pod <pod-name> -o yaml | grep network.alibabacloud.com/allocated-eipAddress
```

访问地址：`http://<EIP>:18789/?token=<your-token>`

### 通过 LoadBalancer 访问

如果使用 ROS 部署，会自动创建 LoadBalancer Service：

```bash
# 获取 LoadBalancer IP
kubectl get svc openclaw-lb

# 访问地址
# http://<LoadBalancer-IP>:18789/?token=<your-token>
```

### 使用 E2B SDK

```python
from e2b_code_interpreter import Sandbox

# 设置环境变量
import os
os.environ['E2B_DOMAIN'] = 'your.domain.cn'
os.environ['E2B_API_KEY'] = 'your-api-key'

# 创建沙箱（从预热池秒级分配）
sbx = Sandbox.create(template="openclaw", timeout=300)
print(f"Sandbox ID: {sbx.sandbox_id}")

# 执行代码
sbx.run_code("a = 1")
result = sbx.run_code("print(f'Value: a = {a}')")
print(result)

# 销毁沙箱
sbx.kill()
```

### 使用休眠/唤醒功能

> **注意**：休眠/唤醒功能需要联系阿里云工作人员开启白名单

**休眠沙箱：**

```bash
kubectl edit sandbox <sandbox-name>
# 修改 spec.paused 为 true
```

**唤醒沙箱：**

```bash
kubectl edit sandbox <sandbox-name>
# 修改 spec.paused 为 false
```

**Python 示例：**

```python
from e2b_code_interpreter import Sandbox

# 创建沙箱并执行代码
sbx = Sandbox.create(template="openclaw", timeout=300)
sbx.run_code("a = 1")
sbx.run_code("print(f'Before pause: a = {a}')")

# 休眠沙箱（保留内存状态）
sandbox_id = sbx.sandbox_id
sbx.beta_pause()
print(f"Sandbox {sandbox_id} paused")

# ... 一段时间后 ...

# 唤醒沙箱（恢复内存状态）
sbx = Sandbox.connect(sandbox_id)
sbx.run_code("print(f'After resume: a = {a}')")  # 变量 a 仍然存在
print(f"Sandbox {sandbox_id} resumed")

# 销毁沙箱
sbx.kill()
```

## NAS 持久化存储（企业版）

企业版支持 NAS 持久化存储，每个 OpenClaw Pod 拥有独立的存储路径：

```
NAS 文件系统 (/openclaw)
├── <pod-name-1>/           # Pod 1 的独立存储
│   ├── data/              # 数据目录
│   └── ...
├── <pod-name-2>/           # Pod 2 的独立存储
│   ├── data/
│   └── ...
└── ...
```

**存储特点：**
- 每个 Pod 挂载到 `/mnt/nas` 目录
- 使用 `subPathExpr: $(POD_NAME)` 实现 Pod 隔离
- 环境变量 `OPENCLAW_DATA_DIR=/mnt/nas/data` 指向数据目录
- Pod 重建后数据自动恢复

## 集成钉钉机器人

### 创建钉钉应用

1. 访问 [钉钉开放平台](https://open.dingtalk.com/)
2. 创建应用，获取 Client ID 和 Client Secret
3. 创建 AI 卡片模板，获取模板 ID
4. 申请权限：`Card.Streaming.Write` 和 `Card.Instance.Write`

### 创建 AppFlow 连接流

1. 使用 AppFlow 模板创建连接流
2. 配置凭证：
   - Client ID 和 Client Secret
   - OpenClaw Gateway Token
3. 配置参数：
   - 公网地址:端口（如 `47.0.XX.XX:18789`）
   - 模板 ID
4. 发布连接流，获取 Webhook URL

### 配置钉钉机器人

1. 在钉钉应用中添加机器人能力
2. 消息接收模式选择「HTTP 模式」
3. 消息接收地址填写 Webhook URL
4. 发布应用版本

详细步骤请参考 [钉钉集成文档](https://open.dingtalk.com/document/org/create-a-group-robot)

## 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                         ACS 集群                            │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │ sandbox-manager  │  │        SandboxSet (预热池)       │ │
│  │  (E2B 兼容 API)  │  │  ┌─────────┐ ┌─────────┐        │ │
│  └────────┬─────────┘  │  │ Sandbox │ │ Sandbox │ ...    │ │
│           │            │  │  + EIP  │ │  + EIP  │        │ │
│           │            │  │  + NAS  │ │  + NAS  │        │ │
│  ┌────────▼─────────┐  │  └─────────┘ └─────────┘        │ │
│  │   ALB Ingress    │  └──────────────────────────────────┘ │
│  └────────┬─────────┘                                       │
└───────────┼─────────────────────────────────────────────────┘
            │
    ┌───────▼───────┐
    │  E2B Client   │
    │ (Python/JS)   │
    └───────────────┘
```

## 组件说明

| 组件 | 说明 |
|------|------|
| **SandboxSet** | 管理 Sandbox 的工作负载，维护预热池实现秒级启动 |
| **Sandbox** | 核心 CRD，管理沙箱实例生命周期，支持 Pause/Resume |
| **sandbox-manager** | 无状态后端组件，提供 E2B 兼容 API |
| **agent-runtime** | Sidecar 组件，提供代码执行、文件操作等功能 |
| **ALB Ingress** | 负载均衡入口，处理 HTTPS 请求 |
| **ImageCache** | 镜像缓存，预先缓存容器镜像加速 Pod 启动 |

## 常见问题

### Q: 沙箱启动慢怎么办？

**A**: 增加预热池副本数或配置镜像缓存：

```bash
# 方式一：增加预热副本
kubectl edit sandboxset openclaw
# 修改 spec.replicas

# 方式二：配置镜像缓存（推荐）
# 在 ACS 控制台创建镜像缓存
```

### Q: 如何查看沙箱状态？

```bash
# 查看所有沙箱
kubectl get sandbox -A

# 查看所有 SandboxSet
kubectl get sandboxset -A

# 查看沙箱详情
kubectl describe sandbox <sandbox-name>
```

### Q: 休眠/唤醒失败？

**A**: 确保满足以下条件：
1. 使用阿里云 ACS 集群
2. 已联系阿里云开启休眠/唤醒功能白名单
3. agent-runtime 组件正常运行

### Q: EIP 访问不通？

**A**: 检查安全组配置：
1. 确认弹性网卡安全组开放了 18789 端口
2. 确认 EIP 已正确绑定
3. 检查防火墙规则

### Q: NAS 数据丢失？

**A**: 检查以下配置：
1. NAS 文件系统已创建
2. 挂载点配置正确
3. 使用 `subPathExpr: $(POD_NAME)` 实现 Pod 隔离

### Q: 域名解析失败？

**A**: 确认以下步骤：
1. ALB 端点已正确配置
2. DNS 解析记录已添加
3. 本地 hosts 配置正确（测试环境）

## 最佳实践

### 1. 资源规划

- **测试环境**：2 核 CPU、4Gi 内存、1 个预热副本
- **生产环境**：4 核 CPU、8Gi 内存、3-5 个预热副本
- **高并发场景**：8 核 CPU、16Gi 内存、10+ 预热副本

### 2. 成本优化

- 合理配置预热副本数，避免资源浪费
- 使用休眠功能暂停不活跃的沙箱
- 配置 NAS 生命周期策略，自动清理过期数据

### 3. 安全加固

- 定期更新 TLS 证书
- 使用强密码作为 Gateway Token
- 配置安全组白名单，限制访问来源
- 定期更新 OpenClaw 镜像版本

### 4. 监控告警

- 监控沙箱启动耗时
- 监控预热池可用副本数
- 监控 NAS 存储使用量
- 监控 EIP 带宽使用情况

## 相关链接

- [OpenKruise Agents 文档](https://openkruise.io/zh/kruiseagents)
- [E2B SDK 文档](https://e2b.dev/docs)
- [阿里云 ACS 文档](https://help.aliyun.com/product/85222.html)
- [OpenClaw 官方仓库](https://github.com/openclaw/openclaw)
- [百炼大模型服务平台](https://bailian.console.aliyun.com/)

## 技术支持

- **钉钉交流群**：在计算巢服务页面可找到钉钉群二维码
- **工单系统**：[提交工单](https://workorder.console.aliyun.com/)
- **文档反馈**：在计算巢服务详情页提交反馈
