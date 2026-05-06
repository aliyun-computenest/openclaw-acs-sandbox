
# OpenClaw Enterprise Edition-Production-Level Deployment Guide

This document describes the **Production** deployment scheme for OpenClaw Enterprise Edition. It is applicable to enterprise customers who have strict requirements on network isolation, security, and high availability.


## Scheme Overview

Production-level deployment is based on the **ACK Managed Cluster VirtualNode (ACS)** architecture and supports high availability in **Zone 3** and **Poseidon TrafficPolicy network isolation**.

-**Cluster Type**:ACK Pro managed cluster VirtualNode(Sandbox pod runs on ACS elastic computing power)
-**Node Management**:ECS node pool operation control components (sandbox-manager, etc.),Sandbox pod elasticity on demand
-**Network isolation**:Poseidon TrafficPolicy security group multi-layer isolation
-**High availability**: deployed in 3 zones, 6 switches (3 services, 3 OpenClaw isolation)

### Network Architecture

-**3 Availability Zone**: Cross-AZ high availability deployment
-**6 switches**:3 service switches and 3 OpenClaw isolation switches
-**Independent NAT Gateway**:OpenClaw the sandbox to use an independent NAT gateway and EIP outbound
-**ALB Ingress**: uses an ALB load balancer as an ingress gateway
-**PrivateZone**: Domain name resolution in VPC

### Network Isolation Policy

Production-level deployments achieve sandbox network isolation through a multi-layer security policy:

**Layer 1: Enterprise security group**
**Level 2: Poseidon TrafficPolicy**
-Refined network strategy at the Kubernetes level through GlobalTrafficPolicy

**Layer 3: Standalone NAT Gateway**
-OpenClaw sandbox uses an independent NAT gateway and EIP outbound network, completely isolated from business traffic

## Preconditions

1. Have an Aliyun account and have completed real-name authentication
2. Prepare TLS certificate files ('fullchain.pem' and 'privkey.pem') for HTTPS access to E2B API
3. Authorize RAM users:
If you are using a RAM user, you need to grant the RAM user the necessary permissions before you can complete the deployment process. Refer to the [authorization documentation](https://help.aliyun.com/zh/compute-nest/security-and-compliance/grant-user-permissions-to-a-ram-user).
The permission policies required to deploy this service include two system permission policies and one custom permission policy. Please contact a user with administrator privileges to grant the following permissions to the RAM user:
**System Permission Policy:**
-AliyunComputeNestUserFullAccess: Permissions for managing the Compute Nest service from the user side,
-AliyunROSFullAccess: Permissions to manage the Resource Orchestration Service (ROS).
**Custom permission policy:**:[policy_prod.json](https://github.com/aliyun-computenest/openclaw-acs-sandbox/blob/main/docs/policy_prod.json)

### Activate Service
If you have not previously used the relevant cloud services, you will be prompted to first activate the services and create the corresponding service roles during deployment, as shown in the figure below.
![img_17.png](images-en/img_17.png)
This step requires permissions with a relatively high risk level (administrator access to cloud services). We recommend using one of the following two methods to enable it:
Note: Activation is a one-time process and is only required for the first time you use the service.
1. Contact a user with administrator privileges to open the Compute Nest service deployment link, and have the administrator follow the prompts to activate the service.
2. Contact a user with administrator permissions to temporarily grant administrator privileges to the RAM user. After the RAM user is authorized, proceed with the activation. The required permission policies are as follows.
Service permission policy for enabling the service: [open_policy.json](https://github.com/aliyun-computenest/openclaw-acs-sandbox/blob/main/docs/open_policy.json)


## Deployment steps

### Step 1: Create a Service Instance

1. Log in to [Compute Nest Console](https://computenest.console.aliyun.com)
2. Find **OpenClaw-ACS-Sandbox Cluster** Service
3. Click **Create Service Instance**


### Step 2: Select Template

At the top of the Create page, select the **Production Environment** template:

-**Test environment**: dual-zone, suitable for quick verification
-**Production Environment**:3 zones are highly available, with network isolation and suitable for official use. (If you need a dual-zone production environment, you can select the "Production Environment-Dual-AZ Edition" template.)


### Step 3: Configure VPC and Availability Zones

| Parameter | Description | Default |
|------|------|--------|
| **Zone 1/2/3** | Select three different zones | Select by region |
| **Select an existing/new VPC** | Create or use an existing VPC | Create a VPC |
| **VPC IPv4 CIDR block** | VPC main CIDR block | '192.168.0.0/16 '|

### Step 4: Configure the Control Switch

Configure the service switch network segment for each of the three zones, which is used for cluster nodes and control components. If you select an existing VPC and the VPC has an additional CIDR block, use the VSWitch corresponding to the VPC main CIDR block:

| Parameter | Description | Default |
| ------ | ----------- | -------- |
| **Control VSwitch subnet CIDR block 1** | Zone 1 CIDR block | '192.168.0.0/24 '|
| **Control switch subnet CIDR block 2** | Zone 2 CIDR block | '192.168.1.0/24 '|
| **Control switch subnet CIDR block 3** | Zone 3 CIDR block | '192.168.2.0/24 '|

### Step 5: Configure the OpenClaw Switch

Configure independent switches for OpenClaw sandbox to achieve physical isolation from the business network:

| Parameter | Description | Default |
| ------ | ------ | -------------------- |
| **OpenClaw PBX network segment 1** | Zone 1 network segment | '192.168.120.0/24 '|
| **OpenClaw PBX network segment 2** | Zone 2 network segment | '192.168.121.0/24 '|
| **OpenClaw PBX network segment 3** | Zone 3 network segment | '192.168.122.0/24 '|

> OpenClaw switches support additional network segments. 3 OpenClaw switch requirements are different from each other


### Step 6: Configure Cluster Parameters

| Parameter | Description | Default |
| ------ | ------ | ----------------- |
| **Service CIDR** | Kubernetes Service CIDR block | '172.16.0.0/16 '|

> The Service CIDR block cannot be the same as the VPC CIDR block and the existing cluster CIDR block, and cannot be modified after creation.

### Step 7: Configure Sandbox Parameters

| Parameter | Description | Required | Default |
| ------ | ------ | --------- | ----------------- |
| **Sandbox access domain name** | Sandbox API access domain name | Default value | agent-vpc.infra |
| **TLS Certificate** | 'fullchain.pem' certificate file | **Required** | |
| **TLS certificate key** | 'privkey.pem' private key file | **Required** | |
| **Whether to configure intranet domain name resolution** | Automatically create PrivateZone | We recommend that you enable | 'true' |
| **Create PrivateZone** | Create or reuse an existing PrivateZone (only displayed when you enable ExistingVPC intranet domain name resolution). If a PrivateZone with the same domain name already exists in the VPC, the template will be automatically scanned. Select "Reuse Existing" | Default | New |
| **Sandbox API Access Key** | Key used to access the Sandbox Management API | Optional | Automatically generated |
| **Sandbox Manager CPU** | sandbox-manager CPU resources | Default | '2' |
| **Sandbox Manager memory** | sandbox-manager memory resources | Default | '4Gi' |
| **Sandbox Manager to schedule to virtual node** | Whether to schedule Sandbox Manager to virtual node (ACS mode). When enabled, Sandbox Manager will run on Serverless virtual node. | By default, enable 'true' |
| **Specify an independent switch for ALB** | After enabling, you can specify an independent switch for ALB, which is isolated from the cluster node switch (effective only for ExistingVPC scenarios) | Optional | |
| **ALB VSwitch ID (Zone 1)** | The private switch used by ALB in Zone 1 must belong to the same VPC. | Optional (required after enabling standalone VSwitch) | |
| **ALB VSwitch ID (Zone 2)** | The private switch used by ALB in Zone 2 must belong to the same VPC. | Optional (required after enabling standalone VSwitch) | |

### Step 8: Configure OpenClaw Parameters

| Parameter | Description | Required |
| ----------------- | ------ | --------- |
| **OpenClaw deployment namespace** | The Kubernetes namespace where the SandboxSet(OpenClaw pod) and TestPod are located. sandbox-manager fixed deployment is sandbox-system is not affected by this parameter. | Default 'default' |

### Step 9: Configure CMS Observability (Optional)

| Parameter | Description | Required |
| ------ | ------ | --------- |
| **Enable CMS observability** | After enabling, the system automatically connects to Alibaba Cloud Monitoring 2.0(ARMS APM) to provide link tracing and performance monitoring for OpenClaw sandboxes. | Disables by default |
| **CMS Workspace name** | The workspace name of CloudMonitor 2.0. You can view the workspace name in the ARMS console (https://arms.console.aliyun.com/). The system will automatically obtain the required AuthToken and Project information from the Workspace without manual configuration. | Required after opening the CMS |

>💡**Note**: After CMS observability is enabled, the system automatically queries Workspace EntryPointInfo (including AuthToken and Project) through 'DATASOURCE::CMS2: ServiceObservability' and injects them into the startup script of the OpenClaw sandbox.

### Step 10: Confirm and Create

1. Click **Next: Confirm Order**
2. Confirm configuration parameters and costs
3. Click **Create** to start the deployment

> Deployment is expected to take **15-22 minutes**. Please be patient.

## Deployment verification

### View service instance status

After the deployment is complete, on the **Service Instance** page of the Compute Nest console, you can see that the instance status changes to **Deployed**.

## Automated testing (no need to configure local environment and domain name resolution, can be used for quick verification)
1. Click the computing nest service instance to find the cluster of ACK contained in the instance.![img_8.png](images-en/img_8.png)
2. Click the cluster container group interface, find the acs-sandbox-test-pod, and click the terminal login![img_9.png](images-en/img_9.png)
3. Test the creation of OpenClaw sandbox.

-Configure the following environment variables to configure the GATEWAY_TOKEN and access API_KEY for the OpenClaw. If you do not perform this step, the default values will be used.
The default value for GATEWAY_TOKEN is: clawdbot-mode-123456
The default value for DASHSCOPE_API_KEY is: sk-****
Domestic refining default baseurl: https://dashscope.aliyuncs.com/compatible-mode/v1
International station hundred refined default baseurl: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
This section is configured in openclaw_template.json
bash
export GATEWAY_TOKEN=****
export DASHSCOPE_API_KEY=****
'''
-Execute 'python create_openclaw.py'
-Wait for the script to complete and get the SandboxId. After the service is ready, it indicates that the OpenClaw started successfully and you can access the OpenClaw Web UI of the corresponding sandbox.
4. Test creation, hibernation, wake-up Openclaw sandbox.
-Execute 'python test_openclaw.py'
5. Wait for the script to verify all functions to pass. If **" Time consuming to create sandbox "** appears in the log, it means that the verification passes.

## SandboxSet configuration

Production-level SandboxSet configuration example:

yaml

apiVersion: agents.kruise.io/v1alpha1
kind: SandboxSet
metadata:
name: openclaw
namespace: ${SandboxNamespace}
spec:
persistentContents:
-file system
replicas: ${OpenClawReplicas}
runtimes:
-name: agent-runtime
template:
metadata:
labels:
app: openclaw
alibabacloud.com/acs: "true"
annotations:
image.alibabacloud.com/enable-image-cache: "true"
"${OpenClawVSwitchId1 },${OpenClawVSwitchId2 },${OpenClawVSwitchId3}"
network.alibabacloud.com/security-group-ids: "${OpenClawIsolationSecurityGroupId}"
network.alibabacloud.com/network-policy-mode: "traffic-policy"
network.alibabacloud.com/enable-network-policy-agent: "true"
spec:
automountServiceAccountToken: false
enableServiceLinks: false
hostNetwork: false
hostPID: false
hostIPC: false
shareProcessNamespace: false
hostname: openclaw
containers:
-name: gateway
image: registry-${RegionId}-vpc.ack.aliyuncs.com/ack-demo/openclaw:2026.3.23-2
securityContext:
readOnlyRootFilesystem: false
runAsUser: 1000
runAsGroup: 1000
command: ["bash", "-c"]
args:
-"exec node openclaw.mjs gateway run --allow-unconfigured"
ports:
-name: gateway
containerPort: 18789
protocol: TCP
-name: runtime
containerPort: 49983
protocol: TCP
environment:
-name: OPENCLAW_CONFIG_DIR
value: /home/node/.openclaw/openclaw.json
-name: KUBERNETES_SERVICE_PORT_HTTPS
value: ""
-name: KUBERNETES_SERVICE_PORT
value: ""
-name: KUBERNETES_PORT_443_TCP
value: ""
-name: KUBERNETES_PORT_443_TCP_PROTO
value: ""
-name: KUBERNETES_PORT_443_TCP_ADDR
value: ""
-name: KUBERNETES_SERVICE_HOST
value: ""
-name: KUBERNETES_PORT
value: ""
-name: KUBERNETES_PORT_443_TCP_PORT
value: ""
resources:
requests:
CPU: 2
memory: 4Gi
limits:
CPU: 2
memory: 4Gi
startup probe:
execute:
command:
-node
--e
-"require('http').get('http://127.0.0.1:18789/healthz', r => process.exit(r.statusCode < 400 ? 0 : 1)).on('error', () => process.exit(1))"
initialDelaySeconds: 1
periodSeconds: 2
failureThreshold: 150
'''

**Important Field Descriptions**

* 'SandboxSet.spec.persistentContents: filesystem'-Keep only the file system during pause/connect
* 'template.spec.automountServiceAccountToken: false' - Pod does not mount Service Account
* 'template.spec.enableServiceLinks: false' - Pod does not inject Service environment variables
* 'o "true"'-use ACS arithmetic
* 'o "true" '-supports pause/connect actions
* 'However "true" '-Enable Network Policy Agent
* '-traffic-policy "'-Use Poseidon TrafficPolicy mode for network isolation

>⚠️ If you expect to use Pause,**be sure not to set** liveness/readiness probes to avoid health check problems during the pause.

**NECESSARY MODIFICATION**

*'

**Brief description of the mechanism**

Envd is enabled on the pod to support the server interface of the E2B SDK. Create the preceding resources kubectl. After the SandboxSet is created, you can see that the sandbox is available.

## Access the OpenClaw Web UI

### Configure Domain Name Resolution



#### Method 1: DNS Resolution (Production Environment)

1. Get the ALB access endpoint.
2. At the DNS service provider, resolve the ALB endpoint to the corresponding domain name with **CNAME** records
3. If you need intranet access, you can add intranet domain name resolution through the PrivateZone

### Mode 2: Local Host Configuration (ALB Public Network Access Required, Only for Temporary Quick Verification)

1. Obtain the ALB access endpoint: View the ALB domain name on the Service Instance Details page
2. Obtain ALB public network IP through 'ping' or'dig'
3. Configure '/etc/hosts':

bash
sudo vim /etc/hosts
# Add the following (replace with the actual ALB IP and Pod name)
39.103.89.43 18789-default--openclaw-abc12.agent-vpc.infra
39.103.89.43 api.agent-vpc.infra
'''

### Domain Name Format

The OpenClaw sandbox is accessed by PrivateZone the wildcard domain name resolution ALB route. The domain name format is as follows:

'''
<port>-<namespace>--<pod-name>.<e2b-domain>?token=<gateway-token>
Up up
Double-hyphen (important!)
'''

**Parameter description**:
-**'port'**:OpenClaw Web UI port, fixed as '18789'
-**'namespace'**: the namespace of the pod. Default value: 'default'
-**'pod-name'**:Sandbox the pod name, such as openclaw-abc12'
-**'e2b-domain'**: E2B domain name configured during deployment
-**'gateway-token'**: the value of GATEWAY_TOKEN configured in the SandboxSet

**Example URL**:
'''
https://18789-default--openclaw-abc12.agent-vpc.infra?token=clawdbot-mode-123456
'''

>⚠The * * double hyphen '--' * * must be used between the namespace and pod-name. using the single hyphen will cause a 502 error.

### Get Sandbox Pod Name

bash
kubectl get pods -n default -l app=openclaw
'''


## Use sandbox Demo
The relevant demo tests can be executed in the acs-sandbox-test-pod of the default namespace of the cluster.

### Create using the Python SDK

1. Install the E2B Python SDK

bash
pip install e2b-code-interpreter
'''

2. Initialize client runtime environment configuration

bash
export E2B_DOMAIN=your.domain
export E2B_API_KEY=your-token
# If you use a self-signed certificate, you also need to configure a trusted CA certificate
export SSL_CERT_FILE=/path/to/ca-fullchain.pem
'''

#### Create a sandbox and configure user information

The GATEWAY_TOKEN of the OpenClaw configured for the user and the API_KEY to access the Hundred Realines,
bash
export GATEWAY_TOKEN=****
export DASHSCOPE_API_KEY=****
'''
Apply for Sandbox for users and configure personal information in the Sandbox. The following code reads the openclaw_template.json configuration template in the acs-sandbox-test-pod and injects the user's independent token and LLM authentication information.

Sample templates can also be referenced.
JSON
{
"agents ": {
"defaults ": {
"model": {
"primary": "bailian/qwen3.5-plus"
},
"workspace": "/root/.openclaw/workspace"
}
},
"models ": {
"mode": "merge ",
"providers ": {
"bailian ": {
"baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1 ",
"apiKey": "${DASHSCOPE_API_KEY} ",
"api": "openai-completions ",
"models ": [
{
"id": "qwen3.5-plus ",
"name": "a thousand questions for all meanings",
"input ": [
"text"
],
"contextWindow": 1000000
"maxTokens": 65536
}
]
}
}
},
"commands ": {
"native": "auto ",
"nativeSkills": "auto ",
"restart": true
"ownerDisplay": "raw"
},
"gateway ": {
"port": 18789
"bind": "lan ",
"controlUi ": {
"allowedOrigins ": [
"*"
],
"dangerouslyAllowHostHeaderOriginFallback": true
"allowInsecureAuth": true
"dangerouslyDisableDeviceAuth": true
},
"auth ": {
"mode": "token ",
"token": "${GATEWAY_TOKEN}"
}
}
}
'''
python
# Import and patch the E2B SDK
import os
import requests
from string import Template
from e2b_code_interpreter import Sandbox

# Note that the never timeout is configured for the user
sbx: Sandbox = Sandbox.create(template="openclaw-sbs", metadata= {
"e2b.agents.kruise.io/never-timeout": "true"
})
print(f"sandbox id: {sbx.sandbox_id}")

# Based on the GATEWAY_TOKEN in the environment variable, DASHSCOPE_API_KEY, EXTERNAL_ACCESS_DOMAIN read
GATEWAY_TOKEN = OS .environ.get("GATEWAY_TOKEN", "clawdbot-mode-123456")
DASHSCOPE_API_KEY = OS .environ.get("DASHSCOPE_API_KEY", "sk-****")


# Render the openclaw-template.json file and overwrite the content of/home/node/.openclaw/openclaw.json in the sandbox to trigger the openclaw to restart and update the configuration.
template_path = "openclaw_template.json"
with open(template_path, "r") as f:
template_content = f.read()

rendered_content = Template(template_content).safe_substitute (
GATEWAY_TOKEN = GATEWAY_TOKEN,
DASHSCOPE_API_KEY = DASHSCOPE_API_KEY,
)

sbx.files.write("/home/node/.openclaw/openclaw.json", rendered_content, user="node")
print("Rendered configuration written to sandbox/home/node/.openclaw/openclaw.json")
print(f"sandbox: {sbx}")
print(f"sandbox id: {sbx.sandbox_id}")
'''

Execute the code to obtain the Sandbox object returned after creation and obtain the details of the newly created Sandbox object.

python
print(f"sandbox: {sbx}")
print(f"sandbox id: {sbx.sandbox_id}")
> The Sandbox object returned after creation contains the details of the newly created Sandbox. The naming format of the sandbox id is '{Namespace}--{Sandbox Name}', where '--' is the K8s namespace of the corresponding resource, followed by the name of the Sandbox.

'''

#### Sleep and Wake
Can refer to the official document: https://help.aliyun.com/zh/cs/user-guide/hibernate-and-wake-up-the-agent-sandbox


> After the sandbox hibernation is successful, the sandbox becomes dormant and the corresponding pod disappears. Note During the hibernation of the sandbox instance, the OpenClaw service will be in an inaccessible state.


## Detailed explanation of network isolation

### TrafficPolicy
TrafficPolicy is used to control network access of Agent applications in the ACK cluster. TrafficPolicy can implement multi-level network policies based on priority, support multiple matching methods such as CIDR, Service, and FQDN, and finely manage pod inbound and outbound traffic.


Please refer to the official document: [Use TrafficPolicy to manage Agent network access](https://help.aliyun.com/zh/ack/ack-managed-and-ack-dedicated/user-guide/use-trafficpolicy-to-manage-agent-network-access)

### Enterprise Security Group Description

OpenClaw security groups are used to control the network access boundaries of Sandbox pods. They must be classified into the following network segments:

#### Network segment classification description

| CIDR block type | Default CIDR block | Corresponding template parameters | Description |
| --------- | --------- | -------- | -------- |
| * * control network segment * * | '192.168.0.0/24', '192.168.1.0/24', '192.168.2.0/24' | control switch subnet network segment 1/2/3 | cluster control plane/switch network segment used by other services, sandbox-manager are deployed under this network segment by default |
| * * OpenClaw network segment * * | '192.168.120.0/24', '192.168.121.0/24', '192.168.122.0/24' | OpenClaw private switch network segment 1/2/3 | The isolated switch network segment where the Agent Sandbox is located needs to be rejected to prevent exchange visits between sandboxes |
| **VPC CIDR block** | '192.168.0.0/16 '| VPC IPv4 CIDR block | VPC main CIDR block, which is included in the control CIDR block and OpenClaw CIDR block |
| **Cloud product network segment** | '100.64.0.0/10 '|-| Alibaba Cloud internal cloud product communication network segment |
| **DNS Service Address** | '100.100.2.136 ', '100.100.2.138' | - | Alibaba Cloud DNS Service Address |
| **Private network segment** | '192.168.0.0/16 ', '172.16.0.0/12', '10.0.0.0/8 '|-| RFC 1918 private network address segment, rejected by default to achieve network isolation |
| **Public network** | '0.0.0.0/0 '|-| Public network exit, low priority release |

#### Group Connectivity Policy

-**In-group isolation**(Sandbox do not communicate with each other)

#### Inbound direction rules

| Priority | Action | Source IP segment | CIDR segment type | Port | Protocol | Description |
| ------- | ------ | --------- | --------- | --------- | ------ | ------ | ------ |
| High | Allow | '192.168.0.0/24', '192.168.1.0/24', '192.168.2.0/24' | Control Network Segment | All | All | sandbox-Access Sandbox of Control Components such as manager |
| - | - | - | - | - | - | - | Add port rules that an application or component expects to access/deny as needed |

#### Outgoing direction rule

| Priority | Action | Destination IP segment | CIDR segment type | Port | Protocol | Description |
| ------- | ------ | ----------- | --------- | --------- | ------ | ------ | ------ |
| High | Allow | '100.64.0.0/10 '| Cloud product CIDR block | Unlimited | All | Access to Alibaba Cloud internal products |
| High | Allow | '192.168.0.0/24 ', '192.168.1.0/24', '192.168.2.0/24 '| Control CIDR Segment | 443, 6443(API Server), 9082(Poseidon) | TCP | Access to Cluster API Server and Poseidon |
| High | Allowed | '192.168.0.0/24 ', '192.168.1.0/24', '192.168.2.0/24 '| Control Network Segment | 53(DNS) | All | DNS Resolution in Cluster |
| High | Allowed | '100.100.2.136 ', '100.100.2.138' | DNS Service Address | 53(DNS) | All | Alibaba Cloud DNS Service |
| High | Reject | '192.168.120.0/24', '192.168.121.0/24', '192.168.122.0/24' | OpenClaw network segments | All | All | * * No exchange of visits between sandboxes * *, realizing network isolation |
| Medium | Deny | '192.168.0.0/16', '172.16.0.0/12', '10.0.0.0/8' | Private Network Segment | All | All | Deny Access to Other Private Network Resources |
| Low | Allow | '0.0.0.0/0 '| Public | All | All | Allow public exits (such as accessing external APIs) |
| - | Allow | '192.168.0.0/24 ', '192.168.1.0/24', '192.168.2.0/24 '| Control CIDR block | On demand | On demand | Optional: Access non-Agent services in the cluster (such as LLM Server) |

> **Note**: The preceding CIDR blocks are default values (corresponding to the default parameters in steps 4 and 5). If the CIDR blocks of the VSwitch are modified during deployment, the IP CIDR blocks in the security group rules must be adjusted synchronously.
### Template Parameters and Network Isolation Concept Quick Look-up Table

| Template parameters | Corresponding concepts | Purpose |
| --------- | --------- | ------ |
| 'VpcCidrBlock' | VPC main CIDR block | Security group rules and TrafficPolicy egress allow(API Server/Poseidon) |
| 'VSwitchCidrBlock1/2/3 '| vsw-downstream (service switch) | sandbox-the CIDR block where the manager, ALB, and ECS nodes are located |
| | 2/3 '| vsw-openclaw (isolated switch) | Sandbox the network segment where the pod is actually running |
| 'OpenClawCidrBlock' | vsw-openclaw summary CIDR block | GlobalTrafficPolicy the deny rule and security group rule |
| 'ServiceCidr' | K8s Service network segment | kube-dns, API Server ClusterIP |
| 'OpenClawIsolationSecurityGroup' | Isolation security group (enterprise) | Sandbox pods are dedicated to each other. By default, pods do not communicate with each other. |
| 'OpenClawNatGateway' 'OpenClawNatEip' | upstream (standalone NAT) | Sandbox Pod outbound traffic isolation |
| 'OpenClawRouteTable' | Independent Routing Table | OpenClaw VSwitch default route points to independent NAT |
| 'OpenClawPodNetworking' | PodNetworking CRD | Bind an isolation security group to an isolation switch to schedule a pod |
| 'GlobalTrafficPolicyApplication' | GlobalTrafficPolicy | Global Deny Inbound OpenClaw CIDR block |
| 'OpenClawTrafficPolicyApplication' | TrafficPolicy | OpenClaw pod refinement ingress/egress control |

## Observable ability
### OpenClaw log
The SLS k8s native capability is provided in the ACK cluster through the loongcollector component, and the collection configuration is created through CR. The corresponding CRD resource name is ClusterAliyunPipelineConfig.

![img_16.png](images-en/img_16.png)

SLS provides out-of-the-box OpenClaw collection configuration, you can access OpenClaw logs through the SLS console, the corresponding SLS Project is k8s-log-${ack cluster id},
-OpenClaw Runtime log (gateway/application)
-Corresponding logstore for openclaw-runtime
-The corresponding acquisition configuration is openclaw-runtime-config
-The CR name in the corresponding K8s cluster is openclaw-runtime-config
-OpenClaw Session audit logs
-Corresponding logstore for openclaw-session
-The corresponding acquisition configuration is openclaw-session-config
-The CR name in the corresponding K8s cluster is openclaw-session-config

For OpenClaw logs, SLS built-in dashboards cover three dimensions: security audit, cost analysis, and behavior analysis:
-OpenClaw behavior analysis market: full volume record and classification statistics of OpenClaw operation behavior
-OpenClaw audit market: from the behavior overview, high-risk commands, prompt injection, data leakage and other dimensions, to provide real-time behavior monitoring, threat identification and after-the-fact traceability capabilities.
-OpenClaw Token to analyze the market: from the overall overview, model dimension trend, session and other dimensions, providing usage monitoring, cost analysis and exception discovery capabilities.

![img_15.png](images-en/img_15.png)

Attention:
The built-in collection configuration is only for demo images. The log path and container filter conditions of custom images may be different. You can modify the configuration in the ACK cluster by modifying the corresponding CR.


## Time Estimate

Estimated about 20 minutes

## Frequently Asked Questions

### How to troubleshoot deployment failure?

1. View the deployment log on the Compute Nest instance details page
2. Enter the ROS console to view the Stack event and find the first' CREATE_FAILED event
3. Locate the root cause according to 'StatusReason'

### kubeconfig can't connect?

If the obtained kubeconfig cannot be connected using an intranet IP, you need to bind an EIP to the cluster or use a VPN to access the cluster.

### Pod starts slowly?

The first startup of the SandboxSet requires pulling the mirror image, which takes about 2-3 minutes. You can view the progress with the following command:

bash
kubectl describe pod -l app=openclaw -n default
'''
