# E2B 架构与配置指南

## 什么是 E2B？

E2B（Environment to Browser）是一个开源的沙箱执行环境协议，允许 AI Agent 在隔离的容器中安全执行代码。阿里云 ACS Agent Sandbox 实现了 E2B 兼容 API，让你可以使用原生 E2B SDK 与沙箱交互。

## 核心架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              你的应用                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  from e2b_code_interpreter import Sandbox                        │   │
│  │  sbx = Sandbox.create(template="openclaw")                       │   │
│  │  sbx.run_code("print('hello')")                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                          E2B SDK 发起请求
                          ① HTTPS://api.zhaoheng.xyz
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              DNS 解析                                    │
│                                                                         │
│   api.zhaoheng.xyz  ──CNAME──>  ALB 公网地址                            │
│                                                                         │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                          ② TLS 证书验证 (*.zhaoheng.xyz)
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           ACS 集群                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    ALB Ingress Controller                        │   │
│  │                    (处理 HTTPS 请求)                              │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│                          ③ 路由到 sandbox-manager                      │
│                                     ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    sandbox-manager                               │   │
│  │                    (E2B 兼容 API Server)                         │   │
│  │                                                                  │   │
│  │  - 管理沙箱生命周期 (create/kill/pause/resume)                   │   │
│  │  - 认证请求 (E2B_API_KEY)                                        │   │
│  │  - 分配预热池中的沙箱                                            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                     │                                   │
│                          ④ 分配沙箱                                     │
│                                     ▼                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    SandboxSet (预热池)                           │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                          │   │
│  │  │ Sandbox │  │ Sandbox │  │ Sandbox │  ...                     │   │
│  │  │ (Pod)   │  │ (Pod)   │  │ (Pod)   │                          │   │
│  │  └─────────┘  └─────────┘  └─────────┘                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 关键概念解析

### 1. E2B_DOMAIN（域名）

**作用**：告诉 E2B SDK 去哪里找 sandbox-manager API。

```python
# SDK 内部会拼接请求地址
# E2B_DOMAIN = "zhaoheng.xyz"
# 
# 请求地址示例：
# - https://api.zhaoheng.xyz/sandboxes          (创建沙箱)
# - https://api.zhaoheng.xyz/sandboxes/{id}     (获取沙箱信息)
# - wss://api.zhaoheng.xyz/sandboxes/{id}/ws    (WebSocket 连接)
```

**配置**：
```bash
export E2B_DOMAIN=zhaoheng.xyz
```

### 2. TLS 证书（*.zhaoheng.xyz）

**为什么需要**：E2B SDK 默认通过 HTTPS 通信，需要证书保证安全。

**证书要求**：
- 必须是 **通配符证书**（`*.zhaoheng.xyz`）
- 覆盖 `api.zhaoheng.xyz`、`*.zhaoheng.xyz` 等子域名

**证书文件**：
- `fullchain.pem`：证书链（包含你的证书 + 中间证书）
- `privkey.pem`：私钥

**申请方式**：
```bash
# Let's Encrypt 免费证书
sudo certbot certonly \
  --manual \
  --preferred-challenges=dns \
  -d "*.zhaoheng.xyz"
```

### 3. CNAME 解析

**作用**：将你的域名指向 ALB 负载均衡器的公网地址。

**配置流程**：

```
1. 获取 ALB 地址
   kubectl get ingress -n sandbox-system
   # NAME              CLASS   HOSTS   ADDRESS                                   PORTS
   # sandbox-manager   alb     *       alb-xxx.cn-hangzhou.alb.aliyuncs.com      80, 443

2. 在域名解析商（如阿里云 DNS）添加 CNAME 记录
   
   记录类型: CNAME
   主机记录: api
   记录值:   alb-xxx.cn-hangzhou.alb.aliyuncs.com
   
   # 这样 api.zhaoheng.xyz 就会解析到 ALB
```

### 4. E2B_API_KEY

**作用**：身份认证，防止未授权访问你的沙箱服务。

**配置**：
```bash
export E2B_API_KEY=e2b_xxxxxxxxxxxx
```

**验证流程**：
```
SDK 请求 → 携带 E2B_API_KEY → sandbox-manager 验证 → 允许/拒绝
```

## 完整配置流程

### 步骤 1：准备域名和证书

```bash
# 1.1 申请通配符证书
sudo certbot certonly --manual --preferred-challenges=dns -d "*.zhaoheng.xyz"

# 1.2 导出证书文件
sudo cp /etc/letsencrypt/live/zhaoheng.xyz/fullchain.pem ./
sudo cp /etc/letsencrypt/live/zhaoheng.xyz/privkey.pem ./
```

### 步骤 2：部署服务（ROS 模板或手动）

部署时填入：
- **E2B 域名**：`zhaoheng.xyz`
- **TLS 证书**：上传 `fullchain.pem`
- **TLS 私钥**：上传 `privkey.pem`
- **E2B_API_KEY**：自动生成或自定义

### 步骤 3：配置 DNS 解析

```bash
# 获取 ALB 地址
kubectl get ingress -n sandbox-system

# 在 DNS 控制台添加 CNAME：
# api.zhaoheng.xyz → alb-xxx.cn-hangzhou.alb.aliyuncs.com
```

### 步骤 4：验证连接

```python
import os
os.environ['E2B_DOMAIN'] = 'zhaoheng.xyz'
os.environ['E2B_API_KEY'] = 'e2b_xxxxxxxxxxxx'

from e2b_code_interpreter import Sandbox

# 创建沙箱
sbx = Sandbox.create(template="openclaw", timeout=300)
print(f"沙箱 ID: {sbx.sandbox_id}")

# 执行代码
result = sbx.run_code("print('Hello from E2B!')")
print(result)

# 销毁沙箱
sbx.kill()
```

## 本地开发（无公网域名）

如果没有公网域名，可以通过 port-forward + hosts 本地测试：

```bash
# 1. 端口转发 sandbox-manager
kubectl port-forward svc/sandbox-manager -n sandbox-system 8000:80

# 2. 配置 hosts
sudo sh -c 'echo "127.0.0.1 api.zhaoheng.xyz" >> /etc/hosts'

# 3. 使用 SDK（需要跳过证书验证或使用 HTTP）
# 注意：本地测试可能需要额外配置
```

## 常见问题

### Q1: 为什么必须用通配符证书？

E2B 协议可能使用多个子域名：
- `api.domain.com` - API 入口
- `{sandbox-id}.domain.com` - 直连沙箱

通配符证书（`*.domain.com`）可以覆盖所有子域名。

### Q2: 证书过期怎么办？

Let's Encrypt 证书有效期 90 天，需要定期续期：

```bash
# 续期
sudo certbot renew

# 更新到集群
kubectl create secret tls sandbox-manager-tls \
  --cert=fullchain.pem \
  --key=privkey.pem \
  -n sandbox-system \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Q3: CNAME 和 A 记录有什么区别？

| 类型 | 值 | 适用场景 |
|------|-----|---------|
| **A 记录** | IP 地址 | ALB 有固定 IP |
| **CNAME** | 域名 | ALB 地址可能变化（推荐） |

ALB 地址可能变化，建议使用 **CNAME**。

### Q4: 可以不用域名吗？

可以，但不推荐。你可以：
1. 直接用 ALB IP 访问（需要修改 SDK 或绕过域名检查）
2. 使用 PrivateZone 在 VPC 内解析（仅限内网访问）

## 组件关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                         E2B 配置项                               │
├─────────────────────────────────────────────────────────────────┤
│  E2B_DOMAIN     │  域名，SDK 用来找 API Server                   │
│  E2B_API_KEY    │  API 密钥，身份认证                            │
│  TLS 证书       │  HTTPS 通信加密                                │
│  CNAME 解析     │  域名 → ALB 地址映射                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      sandbox-manager                             │
├─────────────────────────────────────────────────────────────────┤
│  验证 E2B_API_KEY                                                │
│  管理沙箱生命周期                                                │
│  代理请求到沙箱                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Sandbox (Pod)                               │
├─────────────────────────────────────────────────────────────────┤
│  执行用户代码                                                    │
│  提供文件系统                                                    │
│  支持 Pause/Resume                                               │
└─────────────────────────────────────────────────────────────────┘
```

## 总结

| 配置项 | 作用 | 示例 |
|--------|------|------|
| **E2B_DOMAIN** | SDK 请求的目标域名 | `zhaoheng.xyz` |
| **TLS 证书** | HTTPS 加密通信 | `*.zhaoheng.xyz` 通配符证书 |
| **CNAME 解析** | 域名 → ALB 映射 | `api.zhaoheng.xyz → alb-xxx.alb.aliyuncs.com` |
| **E2B_API_KEY** | API 认证 | `e2b_xxxxxxxxxxxx` |

三者关系：
1. **域名** 是入口地址
2. **证书** 保证通信安全
3. **CNAME** 把域名指向实际服务器（ALB）
4. **API_KEY** 验证你有权限使用服务
