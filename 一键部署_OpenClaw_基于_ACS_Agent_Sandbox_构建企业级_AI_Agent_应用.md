# 一键部署 OpenClaw：基于 ACS Agent Sandbox 构建企业级 AI Agent 应用

**作者：** 宋涛(满瓯)  
**发布时间：** 2月14日  
**浏览量：** 440次

---

## 摘要

OpenClaw 是一款开源、自托管的个人AI 助手，用户可通过聊天界面与其交互并委托执行各类任务。阿里云容器计算服务（ACS）提供的 Agent Sandbox 算力深度打通了 AI 应用与 Kubernetes 及容器生态的集成路径。借助 ACS Agent Sandbox，企业和开发者可以快速构建大规模、高弹性、安全隔离的 Agent 基础设施，加速 AI 智能体在实际场景中的落地与创新。本文将详细介绍如何基于 ACS Agent Sandbox 一键部署 OpenClaw，实现按需休眠与秒级唤醒，并介绍其与钉钉等应用的集成方法。

---

## 1. 基于 ACS Agent Sandbox 部署 OpenClaw 的优势

- **开箱即用、深度集成 Kubernetes 与容器生态**：ACS Agent Sandbox支持以 Kubernetes 作为统一使用界面，提供符合容器标准的 Serverless 算力资源。用户部署 OpenClaw 时，仅需指定应用镜像，即可秒级启动一个功能完备、安全隔离的 AI Agent 运行环境，无需管理底层节点、集群或基础设施。

- **灵活的沙箱休眠与唤醒机制**：ACS Agent Sandbox 支持为OpenClaw实例提供按需使用的休眠和唤醒功能。这意味着当没有任务时，实例可以自动进入休眠状态以节省成本；一旦有新的请求或任务出现，它又能立即被唤醒，并恢复之前的工作状态。

- **强化的安全隔离措施**：基于轻量级虚拟化与容器沙箱技术，ACS Agent Sandbox 为每个 OpenClaw 实例提供独立的运行空间，实现进程、文件系统、网络等维度的严格隔离。

- **具备超大规模资源弹性能力**：基于阿里云容器服务的大规模资源管理和高效极致交付技术，ACS Agent Sandbox能够满足能满足 AI Agent 业务的弹性需求，支持企业级应用部署。

---

## 2. 前提条件

### 2.1 通过创建 ACK/ACS 集群使用ACS算力

您可以通过创建 ACK Pro 或ACS集群使用ACS Agent Sandbox 算力。

- 创建ACK Pro 集群并使用ACS算力，请参见：ACK托管集群Pro版接入ACS算力
- 创建ACS集群，请参见：创建ACS集群

### 2.2 在ACK/ACS集群中安装使用ACS Agent Sandbox的相关组件

- 在集群组件管理中安装 ACK Virtual Node 组件。（若您使用ACS集群，则跳过该步骤即可。）
- 在集群组件管理中安装 ack-agent-sandbox-controller 组件，版本>=v0.5.3。
- 在集群组件管理中安装ack-extend-network-controller组件。

---

## 3. 创建OpenClaw沙箱

### 3.1 方案一：通过Sandbox CR直接创建OpenClaw沙箱

直接创建如下Sandbox资源，请注意在yaml文件中修改如下两个参数完成配置：

- **DASHSCOPE_API_KEY**：OpenClaw使用的大模型访问凭证。您可以在阿里云百炼大模型服务平台前往密钥管理页面，单击创建API-Key获取。

> ⚠️ **警告**：请妥善保管百炼 API-Key。若发生泄露，第三方将有机会冒用您的身份进行恶意使用，产生超出预期的token费用。

> 为在体验初期避免产生超出预期的费用，可购买百炼Coding Plan，该订阅采用固定月费模式，提供月度请求额度。若需使用Coding Plan，可以在服务部署完成后，参考在OpenClaw中使用百炼购买的Coding Plan来修改Base URL。Coding Plan仅支持抵扣qwen3-max-2026-01-23和qwen3-coder-plus模型调用费用，不支持抵扣多模态模型调用费用。

- **GATEWAY_TOKEN**: 自定义参数，配置OpenClaw访问Token。

Sandbox资源中通过声明如下注解，为沙箱自动分配EIP：
```yaml
network.alibabacloud.com/pod-with-eip: "true" # 表示为每个Pod自动分配一个EIP实例
network.alibabacloud.com/eip-bandwidth: "5" # 表示EIP实例带宽为5 Mbps
```

**完整的Sandbox CR配置：**

```yaml
apiVersion: agents.kruise.io/v1alpha1
kind: Sandbox
metadata:
  name: openclaw
  namespace: default
  annotations:
    e2b.agents.kruise.io/should-init-envd: "true"
spec:
  template:
    metadata:
      labels:
        alibabacloud.com/acs: "true" # 使用ACS算力
        app: openclaw
      annotations:
        network.alibabacloud.com/pod-with-eip: "true" # 表示为每个Pod自动分配一个EIP实例
        network.alibabacloud.com/eip-bandwidth: "5" # 表示EIP实例带宽为5 Mbps
    spec:      
      containers:
      - env:
        - name: ENVD_DIR
          value: /mnt/envd
        - name: DASHSCOPE_API_KEY
          value: sk-xxxxxxxxxxxxxxxxx # 替换为您真实的API_KEY
        - name: GATEWAY_TOKEN
          value: clawdbot-mode-123456 # 替换为您希望访问OpenClaw的token
        image: registry.cn-hangzhou.aliyuncs.com/acs-samples/clawdbot:2026.1.24.3
        imagePullPolicy: IfNotPresent
        lifecycle:
          postStart:
            exec:
              command:
              - /bin/bash
              - -c
              - /mnt/envd/envd-run.sh
        name: openclaw
        resources:
          limits:
            cpu: "4"
            memory: 8Gi
          requests:
            cpu: "4"
            memory: 8Gi
        securityContext:
          readOnlyRootFilesystem: false
          runAsGroup: 0
          runAsUser: 0
        startupProbe:
          failureThreshold: 30
          initialDelaySeconds: 5
          periodSeconds: 5
          successThreshold: 1
          tcpSocket:
            port: 18789
          timeoutSeconds: 1
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
        volumeMounts:
        - mountPath: /mnt/envd
          name: envd-volume
      dnsPolicy: ClusterFirst
      initContainers:
      - command:
        - sh
        - /workspace/entrypoint_inner.sh
        env:
        - name: ENVD_DIR
          value: /mnt/envd
        - name: __IGNORE_RESOURCE__
          value: "true"
        image: registry-cn-hangzhou.ack.aliyuncs.com/acs/agent-runtime:v0.0.2
        imagePullPolicy: IfNotPresent
        name: init
        resources: {}
        restartPolicy: Always
        terminationMessagePath: /dev/termination-log
        terminationMessagePolicy: File
        volumeMounts:
        - mountPath: /mnt/envd
          name: envd-volume
      paused: true
      restartPolicy: Always
      schedulerName: default-scheduler
      securityContext: {}
      terminationGracePeriodSeconds: 1
      volumes:
      - emptyDir: {}
        name: envd-volume
```

创建完成后，ACS会为该沙箱创建一个同名的Pod，待Pod启动完成，OpenClaw即处于可用状态。

```bash
$ k get sbx openclaw
NAME       STATUS    AGE   SHUTDOWN_TIME   PAUSE_TIME   MESSAGE
openclaw   Running   57s
```

---

### 3.2 方案二：通过SandboxSet CR创建OpenClaw沙箱预热池（推荐）

#### 3.2.1 为OpenClaw沙箱进行预热

创建如下 SandboxSet 资源，为后续使用OpenClaw沙箱进行预热。

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
                command:
                - /bin/bash
                - -c
                - /mnt/envd/envd-run.sh
      volumes:
      - emptyDir: {}
        name: envd-volume
```

SandboxSet创建完成后，可以看到1个沙箱已经处于可用状态：

```bash
$ k get sandboxsets
NAME       REPLICAS   AVAILABLE   UPDATEREVISION   AGE
openclaw   1          1           65744474f9       22m

$ k get sandboxes
NAME             STATUS    AGE   SHUTDOWN_TIME   PAUSE_TIME   MESSAGE
openclaw-c9wwc   Running   23m
```

对应地，您可以在ACS控制台看到与沙箱同名的Pod已经进入Running状态。

预热池中的沙箱可以直接使用，也可以通过如下方式从预热池中获取沙箱：

#### 3.2.2 通过 SandboxClaim CR 从预热池获取沙箱

创建如下SandboxClaim资源，从SandbosSet中获取沙箱：

```yaml
apiVersion: agents.kruise.io/v1alpha1
kind: SandboxClaim
metadata:
  name: openclaw-claim
spec:  
  templateName: openclaw # 之前创建的SandboxSet 名称
  replicas: 1
  claimTimeout: 1m
  ttlAfterCompleted: 5m
```

SandboxClaim 下发到集群之后，可以通过如下命令获取到 claim 成功的沙箱列表：

```bash
$ kubectl get sandboxclaims
NAME               PHASE       TEMPLATE   DESIRED   CLAIMED   AGE
openclaw-claim     Completed   openclaw   1         1         17s

$ kubectl get sandbox -l agents.kruise.io/claim-name=openclaw-claim
NAME             STATUS    AGE   SHUTDOWN_TIME   PAUSE_TIME   MESSAGE
openclaw-c9wwc   Running   96s
```

沙箱被claim后，SandboSet会迅速将预热池中的副本数补齐，保证预热的沙箱数量。

```bash
$ kubectl get sandboxsets
NAME       REPLICAS  AVAILABLE  UPDATEREVISION   AGE
openclaw   1         1          7f667d7d48       2m2s
```

---

## 4. 通过EIP访问OpenClaw

在前面的介绍中，您成功创建了运行OpenClaw的沙箱实例。您可以通过查询与沙箱同名的Pod Yaml，在`network.alibabacloud.com/allocated-eipAddress`注解中找到系统自动分配的弹性公网IP，如下：

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    ...    
    network.alibabacloud.com/allocated-eip-id: eip-xxxxx0y884ucrevoxxxxx # 系统自动分配的EIP实例ID
    network.alibabacloud.com/allocated-eipAddress: xxx.xxx.xxx.xxx # 系统自动分配的EIP地址
    network.alibabacloud.com/allocated-eni-id: eni-xxxxx563trofuhaxxxxx # 系统自动分配的弹性网卡实例ID
    ...
```

该EIP绑定在系统自动分配的弹性网卡实例上，您可以通过`network.alibabacloud.com/allocated-eni-id`注解中找到系统自动分配的弹性网卡实例，并在弹性网卡控制台中配置安全组规则。请您确保系统所分配的弹性网卡安全组开放了18789端口的访问权限。

确认配置完成后，替换如下访问链接中的IP，即可直接访问 OpenClaw 页面：

```
http://xxx.xxx.xxx.xxx:18789/?token=clawdbot-mode-123456
```

---

## 5. 使用ACS沙箱的休眠唤醒能力

### 5.1 前提条件

联系阿里云工作人员协助您开启休眠、唤醒功能白名单

### 5.2 通过 Sandbox CR 休眠 OpenClaw实例

在您的OpenClaw沙箱运行期间，您可以通过如下命令查看其状态：

```bash
$ kubectl get sandboxes openclaw-c9wwc -o yaml 

apiVersion: agents.kruise.io/v1alpha1
kind: Sandbox
metadata:
  ...
  name: openclaw-c9wwc
spec:  
  template:
    ...
```

您可以通过编辑Sandbox CR的`spec.paused`字段，将其修改为`true`，触发沙箱休眠。

```bash
$ kubectl -n default edit sandbox openclaw-c9wwc  # 修改 `spec.paused` 为 true 

apiVersion: agents.kruise.io/v1alpha1
kind: Sandbox
metadata:
  ...
  name: openclaw-c9wwc
spec:  
  paused: true
  template:
    ...
```

沙箱休眠成功后，可通过 Sandbox CR YAML 查看实例休眠状态。

```bash
$ k get sbx openclaw-c9wwc                                             
NAME             STATUS   AGE   SHUTDOWN_TIME   PAUSE_TIME   MESSAGE
openclaw-c9wwc   Paused   72m
```

OpenClaw实例休眠期间，您的服务将处于不可访问状态。

### 5.3 通过 Sandbox CR 唤醒 OpenClaw实例

您可以通过以下命令唤醒OpenClaw实例。

```bash
kubectl -n default edit sandbox openclaw-c9wwc  # 修改 `spec.paused` 为 false

apiVersion: agents.kruise.io/v1alpha1
kind: Sandbox
metadata:
  ...
  name: openclaw-c9wwc
spec:  
  paused: false
  template:
    ...
```

可通过Sandbox CR YAML 观察实例唤醒状态。

```bash
$ k get sbx openclaw-c9wwc                                             
NAME             STATUS    AGE   SHUTDOWN_TIME   PAUSE_TIME   MESSAGE
openclaw-c9wwc   Running   75m
```

---

## 6. 将OpenClaw集成至钉钉使用

### 6.1 创建钉钉应用

创建钉钉应用需要您的钉钉账号有开发者权限。您可以联系您的组织管理员获取钉钉开放平台的开发权限，具体操作请参见获取开发者权限。

#### 6.1.1 创建应用

1. 访问钉钉开放平台，在应用开发的左侧导航栏中，点击**钉钉应用**，在钉钉应用页面右上角点击**创建应用**。
2. 在创建应用面板，填写应用名称和应用描述，在应用图标上传图标，完成后点击保存。

#### 6.1.2 查看应用 Client ID 和 Client Secret

在左侧菜单选择**凭证与基础信息**，复制Client ID和Client Secret，用于下一步创建连接流。

#### 6.1.3 创建消息卡片

钉钉机器人通过卡片消息支持流式返回结果，您需要创建卡片模板供消息发送使用。

1. 访问卡片平台-模板列表，点击**新建模板**。
2. 在创建模板输入框，填入模板信息，单击创建。
   - 卡片类型：选择**消息卡片**。
   - 卡片模板场景：选择**AI 卡片**。
   - 关联应用：关联应用创建步骤中的应用。
3. 在模拟编辑页面，不要使用预设模板，不需要进行任何额外操作，直接保存并发布模板。然后点击返回模板列表页面。
4. 返回模板列表，复制模板ID，用于创建钉钉连接流使用。

#### 6.1.4 授予应用发送卡片消息权限

创建卡片后，您需要给应用授予发送卡片消息的权限。

1. 访问钉钉应用列表。找到刚刚创建的应用，点击应用名称进入详情页面。
2. 在左侧菜单选择**开发配置 > 权限管理**，在左侧搜索框搜索Card，勾选**AI卡片流式更新权限（Card.Streaming.Write）**和**互动卡片实例写权限（Card.Instance.Write）**，单击**批量申请**。

### 6.2 创建AppFlow连接流

1. 使用AppFlow模板创建连接流，单击**立即使用**进入创建流程。
2. 在连接流的账户授权配置向导页，点击**添加新凭证**。在创建凭证对话框中，填入创建的应用的Client ID 和 Client Secret，并设置一个自定义凭证名称。
   
   > **注意**：在创建凭证时，请确保【Ip白名单】中的IP列表均已被您加入OpenClaw挂载的EIP安全组规则中放行，否则后续可能导致钉钉应用无法访问您的OpenClaw沙箱
   
3. 在连接流的账户授权配置向导页，点击**添加新凭证**。输入您在创建OpenClaw沙箱时配置在GATEWAY_TOKEN 中的Token。
4. 在执行动作配置向导页按照页面提示配置完成后点击下一步。
   - **公网地址：端口**：格式为您的OpenClaw实例分配的EIP:服务端口，例如，EIP为47.0.XX.XX，服务端口为18789，则应填写47.0.XX.XX:18789。
   - **模板ID**：填写步骤三1.3中保存的AI卡片模板ID。
5. 在基本信息配置向导页，填写连接流名称和连接流描述（建议保持默认），完成后点击下一步。
6. 界面提示流程配置成功，复制WebhookUrl，点击发布。

### 6.3 配置钉钉机器人

有了Webhook地址后，接下来您可以在钉钉应用中配置机器人来回答用户问题了。

#### 6.3.1 配置钉钉机器人

1. 访问钉钉应用列表。找到刚刚创建的应用，点击应用名称进入详情页面。
2. 在添加应用能力页面，找到**机器人**卡片，点击**添加**。
3. 在机器人配置页面，打开机器人配置开关，您可以参考下图完成配置。消息接收模式请选择**HTTP模式**，消息接收地址为AppFlow连接流配置发布成功后复制的WebhookUrl。然后点击发布。

> 消息接收模式选择HTTP模式，目前AppFlow仅支持HTTP模式，选择Stream模式会导致无法返回消息。

#### 6.3.2 发布应用版本

应用创建完成后，如果需要将应用供企业内其他用户使用，需要发布一个版本。

1. 单击**应用开发**，在钉钉应用页面，点击目标应用。
2. 在目标应用开发导航栏，单击**版本管理与发布**，在版本管理与发布页面，点击**创建新版本**。进入版本详情页面，输入应用版本号和版本描述信息，选择合适的应用可见范围，完成后点击保存。并在弹窗中点击**直接发布**。

#### 6.3.3 测试机器人

你可以创建群聊或在已有群聊中添加机器人，并与机器人对话，查看效果。

1. 在钉钉群管理中添加机器人。进入钉钉群群设置页面，点击机器人卡片区域，在机器人管理页面，点击**添加机器人**。在添加机器人的搜索文本框中输入目标机器人名称，并选中要添加的机器人。点击**添加**，完成后再点击**完成添加**。
2. 在钉钉群中@机器人进行交流互动。您也可以在钉钉的搜索栏中，输入机器人名称后，在功能页检索到对应机器人，进行私聊互动。
3. 您与机器人的互动都可以在AppFlow连接流中查询运行日志，从而进行调试。

---

## 目录

1. 基于 ACS Agent Sandbox 部署 OpenClaw 的优势
2. 前提条件
   - 2.1 通过创建 ACK/ACS 集群使用ACS算力
   - 2.2 在ACK/ACS集群中安装使用ACS Agent Sandbox的相关组件
3. 创建OpenClaw沙箱
   - 3.1 方案一：通过Sandbox CR直接创建OpenClaw沙箱
   - 3.2 方案二：通过SandboxSet CR创建OpenClaw沙箱预热池（推荐）
     - 3.2.1 为OpenClaw沙箱进行预热
     - 3.2.2 通过 SandboxClaim CR 从预热池获取沙箱
4. 通过EIP访问OpenClaw
5. 使用ACS沙箱的休眠唤醒能力
   - 5.1 前提条件
   - 5.2 通过 Sandbox CR 休眠 OpenClaw实例
   - 5.3 通过 Sandbox CR 唤醒 OpenClaw实例
6. 将OpenClaw集成至钉钉使用
   - 6.1 创建钉钉应用
     - 6.1.1 创建应用
     - 6.1.2 查看应用 Client ID 和 Client Secret
     - 6.1.3 创建消息卡片
     - 6.1.4 授予应用发送卡片消息权限
   - 6.2 创建AppFlow连接流
   - 6.3 配置钉钉机器人
     - 6.3.1 配置钉钉机器人
     - 6.3.2 发布应用版本
     - 6.3.3 测试机器人

---

## 7. OpenClaw 企业版：ROS 一键部署

OpenClaw 企业版提供了完整的 ROS（资源编排服务）一键部署能力，支持自动创建 ACS 集群、配置 NAS 持久化存储、部署 SandboxSet 预热池等企业级功能。

### 7.1 企业版特性

- **一键部署**：通过 ROS 模板自动完成所有资源创建和配置
- **NAS 持久化存储**：每个 Pod 独立的 NAS 存储路径，保留 skills 等数据
- **SandboxSet 预热池**：支持配置预热副本数，确保沙箱快速可用
- **LoadBalancer 公网访问**：自动创建负载均衡器，无需手动配置 EIP

### 7.2 使用 ROS 模板部署

#### 7.2.1 部署前准备

1. **获取百炼 API-KEY**：访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 创建 API-KEY
2. **准备 TLS 证书**：用于 E2B 域名的 HTTPS 访问
3. **确定 E2B 域名**：配置 OpenClaw 访问域名

#### 7.2.2 部署步骤

1. 登录 [ROS 控制台](https://ros.console.aliyun.com/)
2. 选择「创建资源栈」→「使用新资源」→「使用模板创建」
3. 上传 `template.yaml` 文件
4. 填写参数：
   - **可用区**：选择两个不同的可用区（用于高可用）
   - **VPC 配置**：选择新建或使用已有 VPC
   - **E2B 域名**：配置访问域名
   - **TLS 证书**：上传证书和密钥文件
   - **百炼 API-KEY**：从控制台获取
   - **OpenClaw 访问 Token**：自定义访问凭证
   - **预热副本数**：配置 SandboxSet 预热数量（默认 1）

5. 点击「创建」开始部署，约需 5-10 分钟完成

#### 7.2.3 部署输出

部署完成后，在 ROS 资源栈的「输出」页签可获取：

| 输出项 | 说明 |
|--------|------|
| OpenClawAccessUrl | OpenClaw 访问链接，直接复制到浏览器打开 |
| OpenClawEIP | LoadBalancer 公网 IP |
| OpenClawGatewayToken | 访问 Token |
| NASFileSystemId | NAS 文件系统 ID |
| NASMountTargetDomain | NAS 挂载点地址 |

### 7.3 NAS 存储架构

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

**存储路径说明：**
- 每个 Pod 挂载到 `/mnt/nas` 目录
- 使用 `subPathExpr: $(POD_NAME)` 实现 Pod 隔离
- 环境变量 `OPENCLAW_DATA_DIR=/mnt/nas/data` 指向数据目录
- Pod 重建后数据自动恢复

### 7.4 部署后使用

#### 7.4.1 访问 OpenClaw

部署完成后，复制输出中的 `OpenClawAccessUrl` 在浏览器中打开即可使用：

```
http://<LoadBalancer-IP>:18789/?token=<your-token>
```

#### 7.4.2 查看资源状态

使用 kubectl 查看部署状态：

```bash
# 查看 SandboxSet 状态
kubectl get sandboxset -n default

# 查看 Pod 状态
kubectl get pods -l app=openclaw

# 查看 NAS PVC 状态
kubectl get pvc openclaw-nas-pvc

# 查看 LoadBalancer Service
kubectl get svc openclaw-lb
```

#### 7.4.3 扩展预热副本

如需增加预热副本数，可编辑 SandboxSet：

```bash
kubectl edit sandboxset openclaw -n default
# 修改 spec.replicas 字段
```

### 7.5 清理资源

删除 ROS 资源栈即可清理所有创建的资源：

1. 登录 ROS 控制台
2. 找到对应的资源栈
3. 点击「删除」

> **注意**：删除资源栈会同时删除 NAS 文件系统中的数据，请提前备份重要数据。

---

**文章来源：** [ATA 爱獭技术协会](https://ata.atatech.org/articles/11020589221)

**相关阅读：**
- OpenClaw（Clawdbot）产品调研
- 如何在 OpenClaw (Clawdbot/Moltbot) 里配置阿里云百炼 API
- OpenClaw 小白式解读：架构设计与工程实践
- OpenClaw 安全部署，灵魂检查
- 把【内网满血版OpenClaw】接入到钉钉机器人的一些过程
