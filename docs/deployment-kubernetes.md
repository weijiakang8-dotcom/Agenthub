# AgentHub Kubernetes / TLS 部署指南

本文描述将 AgentHub 部署到 Kubernetes，并通过 Ingress NGINX 与 cert-manager 开启 HTTPS 的生产路径。

## 1. 前置条件

- Kubernetes 集群，已配置 `kubectl`
- Ingress NGINX Controller
- cert-manager（可选，用于自动申请 Let's Encrypt 证书）
- 可访问的镜像仓库（默认 `ghcr.io`）
- 已配置域名 DNS 解析，例如 `synplex.xyz`

安装 Ingress NGINX 与 cert-manager 可参考：

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.12.1/deploy/static/provider/cloud/deploy.yaml
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.17.1/cert-manager.yaml
```

## 2. 构建并推送镜像

```bash
REGISTRY=ghcr.io ORG=weijiakang TAG=v0.1.0 PUSH=1 \
  ./scripts/build-images.sh
```

不推送、只本地构建时，把 `PUSH` 设为 `0`。

## 3. 准备密钥

仓库只包含示例文件，不会提交真实密钥。

### 方式 A：从本地 `.env` 生成 Secret

```bash
NAMESPACE=agenthub ENV_FILE=.env ./scripts/create-k8s-secret.sh
```

### 方式 B：使用 External Secrets Operator

先配置 SecretStore，再应用：

```bash
kubectl apply -f k8s/external-secret.example.yaml
```

需要把 `secretStoreRef` 和 `remoteRef` 改成真实环境。

## 4. 配置 TLS 证书

### 自动签发（cert-manager）

创建 ClusterIssuer：

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: you@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-account-key
    solvers:
      - http01:
          ingress:
            class: nginx
```

然后应用 TLS Ingress：

```bash
kubectl apply -f k8s/08-tls-ingress.yaml
```

`k8s/08-tls-ingress.yaml` 使用以下约定：

- 域名：`synplex.xyz`
- Certificate Secret：`synplex-xyz-tls`
- ClusterIssuer：`letsencrypt-prod`
- 自动 HTTP → HTTPS 跳转

### 手动上传已有证书

```bash
kubectl -n agenthub create secret tls synplex-xyz-tls \
  --cert=synplex.xyz_bundle.crt \
  --key=synplex.xyz.key
```

如果使用手动证书，请删除 `Certificate` 资源或改为 `secretName` 引用现有 Secret。

## 5. 部署应用

推荐使用部署脚本：

```bash
REGISTRY=ghcr.io ORG=weijiakang TAG=v0.1.0 \
  ./deploy/k8s-deploy.sh
```

也可以手动执行：

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/01-config.yaml
kubectl apply -f k8s/02-postgres.yaml
kubectl apply -f k8s/03-redis.yaml
kubectl apply -f k8s/04-backend.yaml
kubectl apply -f k8s/05-frontend.yaml
kubectl apply -f k8s/06-ingress.yaml
kubectl apply -f k8s/07-hpa.yaml
kubectl apply -f k8s/08-tls-ingress.yaml
```

注意：`04-backend.yaml` 中的镜像默认是 `weijiakang/agenthub-backend:latest`，部署脚本会用 `REGISTRY` / `ORG` / `TAG` 做替换。

## 6. 验证部署

```bash
kubectl -n agenthub get pods
kubectl -n agenthub get svc
kubectl -n agenthub get ingress
kubectl -n agenthub get certificate
```

期望状态：

- `backend`、`celery-worker`、`frontend`、`postgres`、`redis` 均 `Running`
- `agenthub-tls` Ingress 有公网地址
- `synplex-xyz-tls` Certificate 状态为 `Ready=True`

访问：

- Web：`https://synplex.xyz`
- API：`https://synplex.xyz/api`
- Swagger：`https://synplex.xyz/docs`（如生产环境未关闭）
- Metrics：`/metrics`

## 7. 常见问题

### Certificate 一直未 Ready

```bash
kubectl -n agenthub describe certificate synplex-xyz-tls
kubectl -n agenthub describe certificaterequest
kubectl -n agenthub describe order
```

通常是域名未解析到 Ingress 公网地址，或 HTTP-01 challenge 被防火墙拦截。

### Ingress 无地址

确认 Ingress NGINX Controller 是否已安装并暴露 LoadBalancer：

```bash
kubectl -n ingress-nginx get svc ingress-nginx-controller
```

### 镜像拉取失败

确认 `REGISTRY` / `ORG` / `TAG` 与镜像仓库一致，并配置 imagePullSecret。

### 数据库迁移失败

查看 backend initContainer 日志：

```bash
kubectl -n agenthub logs deploy/backend -c migrate
```
