# 在ACS集群中使用 E2B 管理安全沙箱

## 概述

E2B 是一个流行的开源安全沙箱框架，提供了一套简单易用的 Python 与 JavaScript SDK 供用户对安全沙箱进行创建、查询、执行代码、请求端口等操作。
ack-sandbox-manager组件是一个兼容 E2B 协议的后端应用，使用户在任何 K8s 集群中一键搭建一个性能媲美原生 E2B 的沙箱基础设施。

本服务提供了在ACS 集群中快速搭建安全沙箱的解决方案，支持使用 E2B 协议进行交互，并默认准备了openclaw沙箱。

预计部署时间： 10分钟

## 前提准备

标准的 E2B 协议需要一个域名（E2B_DOMAIN）来指定后端服务。为此，您需要准备一个自己的域名。
E2B 客户端必须通过 HTTPS 协议请求后端，因此还需要为服务申请一个通配符证书。

以下介绍了测试场景下的域名和证书准备步骤，生成的fullchain.pem和privkey.pem文件在后续部署环节会用到。

#### 准备域名
- 测试场景中，为了方便验证，可以使用测试域名，比如示例：agent-vpc.infra,

#### 获取自签名证书
通过脚本[generate-certificate.sh](https://github.com/openkruise/agents/blob/master/hack/generate-certificates.sh) 创建自签名证书。 您可以通过以下命令查看脚本的使用方法。
```bash
$ bash generate-certificates.sh --help

Usage: generate-certificates.sh [OPTIONS]

Options:
  -d, --domain DOMAIN     Specify certificate domain (default: your.domain.com)
  -o, --output DIR        Specify output directory (default: .)
  -D, --days DAYS         Specify certificate validity days (default: 365)
  -h, --help              Show this help message

Examples:
  generate-certificates.sh -d myapp.your.domain.com
  generate-certificates.sh --domain api.your.domain.com --days 730
```
生成证书的命令示例：
```bash
./generate-certificates.sh --domain agent-vpc.infra --days 730
```
完成证书生成后，您会得到以下文件：

- fullchain.pem：服务器证书公钥
- privkey.pem：服务器证书私钥
- ca-fullchain.pem：CA 证书公钥
- ca-privkey.pem：CA 证书私钥
该脚本会同时生成单域名（your.domain）与泛域名（*.your.domain）证书，兼容原生 E2B 协议与 OpenKruise 定制 E2B 协议。

## 部署流程

1. 打开计算巢服务[部署链接](https://computenest.console.aliyun.com/service/instance/create/cn-hangzhou?type=user&ServiceId=service-47d7c54c78604e0bbe79)
2. 填写相关部署参数、选择部署地域、ACS集群的Service CIDR, 专有网络配置![img_1.png](img_1.png) 
3. 填写E2B 域名配置，E2B的访问域名配置为上述前提准备阶段的域名， 
   1. TLS 证书选择fullchain.pem文件
   2. TLS 证书私钥选择privkey.pem文件
         ![img.png](img.png)
4. 会生成访问E2B API的 E2B_API_KEY
5. sandbox-manager 组件默认的CPU和内存配置默认为2C, 4Gi, 可以按需调整
6. 配置完成后，点击确认订单
7. 部署成功后，在服务实例的详情页也可以查看E2B_API_KEY、E2B_DOMAIN等信息
         ![img_4.png](img_4.png)

## 使用沙箱
 
 部署完成后，会得到一个对应的ACS集群，ACS集群中在sandbox-system命名空间下有sandbox-manager的Deployment，用于管理沙箱。
 通过以下流程验证E2B服务已经正常运行，并介绍沙箱使用Demo.

### 配置域名的解析

#### 本地配置Host: 用于快速验证
1. 获取ALB的访问端点：ack-sandbox-manager 集群中使用Alb作为Ingress，在服务实例详情页，可以找到找到ACS控制台的链接，点击链接查看sandbox-manager的网关，可以获取ALB的访问端点，如下图所示
![img_2.png](img_2.png)
2. 获取Alb端点对应的公网地址：本地通过ping ALB的访问端点得到公网Ip 
```ping alb-xxxxxx```
3. 将ALB的公网地址和域名配置到本地host：```echo "ALB_PUBLIC_IP api.E2B_DOMAIN" >> /etc/hosts```
示例为： 
```xx.xxx.xx.xxx api.agent-vpc.infra```
4. 配置完Host后，无需配置DNS解析，在本地就可以管理E2B沙箱，具体使用方式，参考“使用沙箱demo”章节。

#### 配置DNS解析：用于生产环境
1. 获取ALB的访问端点：
ack-sandbox-manager 集群中使用Alb作为Ingress，在服务实例详情页，可以找到找到ACS控制台的链接，点击链接查看sandbox-manager的网关，可以获取ALB的访问端点，如下图所示
![img_2.png](img_2.png)
2. 配置DNS解析： 
请将Alb的访问端点 以 CNAME 记录类型解析到对应域名，
![img_5.png](img_5.png)
3. 如需通过内网访问，可以通过PrivateZone 为E2B 添加内网域名。(如果部署时选择了新建VPC, 已经为您自动配置了PrivateZone，后续只需要添加解析记录)【可选】

### 使用沙箱demo

#### 创建沙箱
当前已默认帮创建了沙箱。以下仅为参考
注意：以下示例中是从杭州地域拉取镜像，若部署在其他地域，首次拉取耗时较长大约需要5分钟，请耐心等待，也可替换image中的regionId为其他地域。
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
  replicas: 1
  template:
    metadata:
      labels:        
        alibabacloud.com/acs: "true" # 使用ACS算力
        app: openclaw
      annotations:
        network.alibabacloud.com/pod-with-eip: "true" # 表示为每个Pod自动分配一个EIP实例
        network.alibabacloud.com/eip-bandwidth: "5" # 表示EIP实例带宽为5 Mbps
    spec:
      initContainers:
        - name: init
          image: registry-cn-hangzhou.ack.aliyuncs.com/acs/agent-runtime:v0.0.2
          imagePullPolicy: IfNotPresent
          command: [ "sh", "/workspace/entrypoint_inner.sh" ]
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
              value: sk-xxxxxxxxxxxxxxxxx # 替换为您真实的API_KEY
            - name: GATEWAY_TOKEN 
              value: clawdbot-mode-123456 # 替换为您希望访问OpenClaw的token
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
                command: [ "/bin/bash", "-c", "/mnt/envd/envd-run.sh" ]        
      terminationGracePeriodSeconds: 1
      volumes:
        - emptyDir: { }
          name: envd-volume
```
通过kubectl 创建上述资源，SandboxSet创建完成后，可以看到1个沙箱已经处于可用状态：
![img_6.png](img_6.png)


#### 设置环境变量

```bash
export E2B_DOMAIN=your.domain.cn
export E2B_API_KEY=xxxxx

export SSL_CERT_FILE=/path/to/ca-fullchain.pem #使用本地配置Host的方式进行验证时，需要声明此变量

```

#### 执行代码
以下脚本演示了沙箱的删除，Sandboxset 会从预热池中快速分配一个沙箱实例，完成分配的同时，SandboxSet会删除旧的沙箱
```python
import os

# Import the E2B SDK
from e2b_code_interpreter import Sandbox

# Create a sandbox using the E2B Python SDK
# 这里 template 名字要和 SandboxSet 名字保持一致
sbx = Sandbox.create(template="openclaw", timeout=60,  
                     metadata={
                        "e2b.agents.kruise.io/never-timeout": "true"
                    }
)
print(f"sandbox id: {sbx.sandbox_id}")

sbx.kill()
print(f"sandbox {sbx.sandbox_id} killed")
```
预期输出
```html
sandbox id: default--openclaw-22j5l
sandbox default--openclaw-22j5l killed

```
当预期返回中有沙箱Id时，可以认为E2B 服务已经正常运行了