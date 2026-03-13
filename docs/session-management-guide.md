# OpenClaw 企业版 - Session 与用户管理指南

## 概述

OpenClaw 企业版基于阿里云 ACS 集群 + NAS 共享存储部署，采用 **Session ID 映射** 机制实现用户数据的持久化和跨 Pod 访问。本文档介绍部署完成后如何通过 Session ID 管理用户和 Pod。

## 架构说明

```
用户浏览器 (Session ID 保存在 Cookie)
      │
      ▼
LoadBalancer (公网 IP:18789)
      │
      ├──▶ Pod A ──┐
      │            │──▶ NAS 共享存储
      └──▶ Pod B ──┘      │
                           ├── /moltbot-shared/agents/main/sessions/
                           │     ├── <session-id-1>.jsonl   ← 用户 1
                           │     ├── <session-id-2>.jsonl   ← 用户 2
                           │     └── ...
                           └── /data/   ← OPENCLAW_DATA_DIR
```

**核心设计**:
- 所有 Pod 通过 NAS 共享 `/root/.moltbot` 和 `/mnt/nas` 目录
- 每个用户的 Session 以 UUID 命名，数据文件存储在 NAS 上
- LoadBalancer 将请求分发到任意 Pod，任意 Pod 都能读取任意 Session 的数据
- Pod 删除或重建后，用户凭 Session ID 即可恢复完整工作状态

## 访问 OpenClaw

部署完成后，ROS Stack Outputs 中会输出访问地址：

```
OpenClawAccessUrl: http://<EIP>:18789/?token=<your-token>
```

在浏览器中打开此地址即可使用。首次连接时系统会自动分配 Session ID 并存储在浏览器中。

## Session 管理操作

### 查看当前所有 Session

```bash
# 进入任意 Pod 查看 NAS 上的 Session 文件
kubectl exec -it <pod-name> -c openclaw -- ls -la /root/.moltbot/agents/main/sessions/
```

输出示例：

```
-rw-r--r-- 1 root root  4096 Mar 12 14:26 3a2f325b-7c8d-4e0f-a123-456789abcdef.jsonl
-rw-r--r-- 1 root root  2048 Mar 12 15:30 7b1c9d0e-2f3a-4b5c-d678-9e0f1a2b3c4d.jsonl
```

每个 `.jsonl` 文件对应一个用户 Session。

### 查看特定 Session 内容

```bash
kubectl exec -it <pod-name> -c openclaw -- cat /root/.moltbot/agents/main/sessions/<session-id>.jsonl
```

### 清理过期 Session

```bash
# 删除 7 天前的 Session 文件
kubectl exec -it <pod-name> -c openclaw -- \
  find /root/.moltbot/agents/main/sessions/ -name "*.jsonl" -mtime +7 -delete
```

### 备份 Session 数据

Session 数据全部存储在 NAS 上，可以通过以下方式备份：

```bash
# 从 Pod 中打包 Session 数据
kubectl exec <pod-name> -c openclaw -- \
  tar czf /tmp/sessions-backup.tar.gz -C /root/.moltbot/agents/main/sessions/ .

# 拷贝到本地
kubectl cp <pod-name>:/tmp/sessions-backup.tar.gz ./sessions-backup.tar.gz -c openclaw
```

## Pod 管理

### 查看 Pod 状态

```bash
kubectl get sandboxset,pods -l app=openclaw -o wide
```

### 扩缩容

根据用户并发量调整 Pod 数量：

```bash
# 扩容到 N 个副本
kubectl patch sandboxset openclaw --type='merge' -p '{"spec":{"replicas": N}}'

# 查看扩容进度
kubectl get pods -l app=openclaw -w
```

**建议**: 每个 Pod 支持约 10-20 个并发 Session，按实际负载调整。

### Pod 故障恢复

Pod 被删除或故障时，SandboxSet 会自动创建新 Pod：

```bash
# 手动删除故障 Pod（SandboxSet 会自动重建）
kubectl delete pod <pod-name>

# 观察重建过程
kubectl get pods -l app=openclaw -w
```

新 Pod 启动后会自动挂载 NAS，用户无需任何操作即可继续使用。

## 存储结构

NAS 挂载在每个 Pod 内的路径如下：

| Pod 路径 | NAS 子路径 | 用途 |
|----------|-----------|------|
| `/root/.moltbot` | `moltbot-shared/` | Session 状态、Agent 配置 |
| `/mnt/nas` | `/`（根目录） | 通用数据存储 |

### 查看 NAS 使用情况

```bash
kubectl exec <pod-name> -c openclaw -- df -h /mnt/nas
kubectl exec <pod-name> -c openclaw -- du -sh /root/.moltbot/agents/main/sessions/
```

## 用户数据生命周期

```
1. 用户首次访问
   └─▶ 系统生成 Session ID (UUID) → 写入 NAS
   └─▶ Session ID 存入浏览器 Cookie

2. 用户后续访问
   └─▶ 浏览器携带 Session ID → LB 分发到任意 Pod
   └─▶ Pod 从 NAS 读取对应 Session 文件 → 恢复状态

3. Pod 故障/删除
   └─▶ SandboxSet 自动重建 Pod → 挂载同一 NAS
   └─▶ 用户无感知，Session 数据完整保留

4. 用户清理/下线
   └─▶ 管理员删除 NAS 上对应的 Session 文件
   └─▶ 或通过定时任务自动清理过期 Session
```

## 数据隔离与安全

### Session 隔离机制

用户之间的数据隔离在**应用层**实现，而非存储层：

- 每个用户连接时，OpenClaw 分配一个随机 UUID 作为 Session ID
- OpenClaw 进程只加载请求中携带的 Session ID 对应的数据文件
- 正常使用下，用户 A 不会看到用户 B 的数据

### 隔离边界

需要注意的是，当前方案**不是**强制权限隔离：

| 层面 | 是否隔离 | 说明 |
|------|---------|------|
| Session 数据文件 | 应用层隔离 | 每个 Session 一个独立 `.jsonl` 文件，OpenClaw 按 Session ID 加载 |
| NAS 文件系统 | **共享** | 所有 Session 文件在同一个 NAS 目录下，所有 Pod 均可读写 |
| 访问 Token | **共享** | 所有用户使用相同的 `GATEWAY_TOKEN`，没有用户级认证 |
| Pod 进程 | **共享** | 多个 Session 可能由同一个 Pod 进程处理 |

**安全依赖点**: Session ID 是 UUID（128 位随机数），碰撞概率极低，正常情况下不可被猜测。

### 适用场景建议

- **企业内部/团队使用**: 当前方案已足够，团队成员互信，Session ID 的随机性提供了基本隔离
- **面向外部用户**: 建议在 LoadBalancer 前增加用户认证层（如 OAuth2 网关），将用户身份与 Session ID 绑定

## NAS 存储挂载详情

NAS 只有一个 PVC（`openclaw-nas-pvc`），在每个 Pod 内挂载到两个路径：

### NAS 物理结构

```
NAS 文件系统 (1cdc749ffd-xxg37.cn-beijing.nas.aliyuncs.com)
/                               ← NAS 根目录
├── moltbot-shared/             ← subPath, 挂载到 /root/.moltbot
│   ├── agents/
│   │   └── main/
│   │       └── sessions/
│   │           ├── d7536c03-217f-4b4f-ad5f-5ce467be42a8.jsonl  ← 用户 Session
│   │           └── ...
│   └── (其他 Agent 配置)
└── data/                       ← OPENCLAW_DATA_DIR
    └── (通用数据)
```

### Pod 内挂载映射

| Pod 内路径 | 存储类型 | NAS subPath | 用途 |
|-----------|---------|-------------|------|
| `/root/.moltbot` | NAS PVC | `moltbot-shared` | Session 状态、Agent 配置、对话历史（持久化） |
| `/mnt/nas` | NAS PVC | 无（根目录） | 通用数据目录，`OPENCLAW_DATA_DIR=/mnt/nas/data`（持久化） |
| `/mnt/envd` | emptyDir | - | envd 运行时临时文件（Pod 销毁即丢失） |

### 为什么用两个挂载点

- `/root/.moltbot` 使用 `subPath: moltbot-shared`：将 Session 数据集中存放在 NAS 的固定子目录下，避免与其他数据混杂
- `/mnt/nas` 挂载根目录：提供通用的持久化存储空间，OpenClaw 运行产生的文件（如用户上传、代码产物）存放于此

两个挂载点指向同一个 NAS PVC，数据最终都在同一个 NAS 文件系统上。

### 存储容量

NAS（通用型）按实际使用量计费，无需预分配容量。单个 Session 文件通常几 KB 到几 MB（取决于对话长度），正常使用下存储增长缓慢。

## 常见问题

### 用户反馈数据丢失

1. 确认用户浏览器 Cookie 中的 Session ID 是否还在（清除浏览器数据会丢失 Session ID）
2. 检查 NAS 上对应 Session 文件是否存在：
   ```bash
   kubectl exec <pod-name> -c openclaw -- ls -la /root/.moltbot/agents/main/sessions/ | grep <session-id>
   ```
3. 如果文件存在但用户无法访问，检查 Pod 日志：
   ```bash
   kubectl logs <pod-name> -c openclaw --tail=50
   ```

### NAS 存储空间不足

```bash
# 查看存储使用情况
kubectl exec <pod-name> -c openclaw -- df -h /mnt/nas

# 清理旧 Session 释放空间
kubectl exec <pod-name> -c openclaw -- \
  find /root/.moltbot/agents/main/sessions/ -name "*.jsonl" -mtime +30 -delete
```

### Pod 长时间未就绪

新 Pod 通常需要 60-90 秒完成启动（包括 NAS 挂载和 envd 初始化）。如果超过 3 分钟仍未就绪：

```bash
# 查看 Pod 事件
kubectl describe pod <pod-name>

# 查看容器日志
kubectl logs <pod-name> -c openclaw
kubectl logs <pod-name> -c init
```
