# OpenClaw ACS Sandbox 部署

基于阿里云 ACS (Agent Compute Service) 和 ROS (资源编排服务) 的 OpenClaw 一键部署方案。

## 功能特性

- **一键部署**：通过 ROS 模板自动创建 ACS 集群、NAS 存储、网络配置等全部资源
- **SandboxSet 预热池**：基于 OpenKruise 的 SandboxSet 实现沙箱预热，Pod 秒级启动
- **镜像缓存加速**：支持 ACS 镜像缓存功能，大幅缩短首次启动时间
- **多地域支持**：自动选择最优镜像源，支持北京、上海、杭州、深圳、新加坡等地域
- **PrivateZone 集成**：新建 VPC 时自动创建 PrivateZone，实现 E2B 域名内网解析

## 快速开始

### 方式一：计算巢部署（推荐）

直接通过阿里云计算巢控制台部署，无需任何配置。

### 方式二：ROS 控制台部署

1. 登录 [ROS 控制台](https://ros.console.aliyun.com/)
2. 创建资源栈，上传 `template.yaml`
3. 填写参数并确认部署

### 方式三：命令行部署

```bash
# 使用部署管理工具
python ros_stack_manager.py create --name openclaw-demo --region cn-hangzhou --params parameters.yaml
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `template.yaml` | ROS 主模板，包含完整的资源定义 |
| `ros_stack_manager.py` | 部署管理工具，支持创建、更新、删除、状态查询等操作 |
| `parameters.yaml` | 参数示例文件 |
| `docs/` | 详细部署文档 |

## 前置条件

- 镜像缓存白名单：[提交工单](https://smartservice.console.aliyun.com/service/create-ticket) 申请开通
- 百炼 API Key：[获取方式](https://developer.aliyun.com/article/1655158)
- TLS 证书：为 E2B 域名准备有效的 TLS 证书

## 文档

- [完整部署指南](docs/deployment-guide.md)
- [一键部署说明](一键部署_OpenClaw_基于_ACS_Agent_Sandbox_构建企业级_AI_Agent_应用.md)

## License

Apache License 2.0
