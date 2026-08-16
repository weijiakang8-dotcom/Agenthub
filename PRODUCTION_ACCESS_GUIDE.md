# AgentHub Production Access Guide

本文件用于帮助恢复生产服务器控制权并关闭 Phase 5.5 的 P0 公网暴露问题。

## 1. 当前服务器信息

- 公网 IP：`193.112.130.181`
- 域名：`synplex.xyz`
- 域名解析：DNS-over-HTTPS 显示 `synplex.xyz -> 193.112.130.181`
- 已确认公网端口：
  - `22` SSH
  - `80` HTTP
  - `443` HTTPS
  - `8000` Backend
  - `5433` PostgreSQL
  - `6379` Redis
  - `9090` Prometheus
  - `3000` Grafana
  - `16686` Jaeger
  - `4317` / `4318` OTel
  - `1025` / `8025` MailHog

## 2. 当前 SSH 失败原因

已尝试：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 ubuntu@193.112.130.181
```

结果：

```text
Permission denied (publickey,password)
```

可能原因：

- 当前机器没有加载该服务器的 SSH 私钥
- SSH 用户名可能不是 `ubuntu`
- 服务器没有配置当前机器的公钥
- 服务器只允许特定来源 SSH

以上均标记为 `UNVERIFIED`。

## 3. 需要确认的 SSH 用户名

候选用户名：

- `ubuntu`（Ubuntu Server 常见）
- `root`（部分云厂商可能允许，但风险高）
- 自定义管理员用户名

当前无法确认正确用户名，标记 `UNVERIFIED`。

## 4. SSH Key 配置要求

在本地执行：

```bash
ssh-keygen -t ed25519 -C "agenthub-production"
```

查看公钥：

```bash
cat ~/.ssh/id_ed25519.pub
```

将公钥添加到服务器的：

```text
~/.ssh/authorized_keys
```

本地配置 `~/.ssh/config`：

```text
Host agenthub-prod
    HostName 193.112.130.181
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

权限要求：

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/id_ed25519
chmod 644 ~/.ssh/id_ed25519.pub
```

## 5. 腾讯云安全组需要开放/关闭的端口

### 允许公网访问

- `22` SSH，建议限制来源 IP
- `80` HTTP
- `443` HTTPS

### 必须关闭或改为内网访问

- `8000` Backend
- `5433` PostgreSQL
- `6379` Redis
- `9090` Prometheus
- `3000` Grafana
- `16686` Jaeger
- `4317` / `4318` OTel
- `1025` / `8025` MailHog

这些服务应只通过 Docker 内部网络访问，或通过 SSH tunnel 访问。

## 6. 如何通过腾讯云控制台进入服务器

1. 登录腾讯云控制台
2. 进入 CVM 或 Lighthouse
3. 找到 `193.112.130.181`
4. 使用“登录 / 远程连接”
5. 选择 VNC / WebShell 登录
6. 登录后确认当前用户：

```bash
whoami
hostname
```

## 7. 进入服务器后第一批应该执行的检查命令

```bash
whoami
hostname
uptime
uname -a
df -h
free -h
cd ~/agenthub
git status
git rev-parse --short HEAD
docker --version
docker compose version
docker ps
sudo ss -lntp
sudo ufw status
sudo iptables -L -n
```

## 8. 如何确认当前 Docker Compose 版本

```bash
docker compose version
docker-compose --version
```

应优先使用：

```bash
docker compose
```

## 9. 如何确认当前公网监听端口

```bash
sudo ss -lntp
```

重点看 `Local Address` 是否为 `0.0.0.0` 或 `::`。

从外部机器验证：

```bash
nc -zv 193.112.130.181 22
nc -zv 193.112.130.181 80
nc -zv 193.112.130.181 443
nc -zv 193.112.130.181 5433
nc -zv 193.112.130.181 6379
```

## 10. 如何安全重新部署最新 Compose

```bash
cd ~/agenthub
git fetch origin
git checkout main
git pull --ff-only origin main
docker compose -f docker/docker-compose.yml config --quiet
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
curl -fsS http://127.0.0.1:8000/health
```

不要在生产服务器未确认 `git status` 干净前盲目 `git pull`。

## 11. 如何验证 PostgreSQL / Redis 等内部服务已经不再公网暴露

服务器内部：

```bash
sudo ss -lntp | grep -E '5433|6379|9090|3000|16686|4317|4318|1025|8025|8000'
```

期望这些端口只监听 `127.0.0.1`，不监听 `0.0.0.0`。

外部验证：

```bash
nc -zv 193.112.130.181 5433
nc -zv 193.112.130.181 6379
nc -zv 193.112.130.181 9090
nc -zv 193.112.130.181 3000
nc -zv 193.112.130.181 16686
```

成功标准：从公网连接失败或超时。

## 12. 如何验证 HTTPS

```bash
curl -I https://synplex.xyz
curl -I http://synplex.xyz
echo | openssl s_client -connect synplex.xyz:443 -servername synplex.xyz
```

目标：

- HTTP 返回 301/308 跳转到 HTTPS
- HTTPS 返回 `200`
- 证书链有效
- TLS 1.2 / 1.3

## 13. 如何回滚

### 应用代码回滚

```bash
cd ~/agenthub
git log --oneline -10
git checkout <target-commit>
docker compose -f docker/docker-compose.yml up -d --build
```

### Docker 镜像回滚

如果使用带 tag 的镜像：

```bash
docker compose -f docker/docker-compose.yml up -d backend:<tag>
```

### 数据库回滚

```bash
cd ~/agenthub/backend
alembic downgrade -1
```

生产数据库回滚前必须先备份。

## 当前限制

- 正确 SSH 用户名：`UNVERIFIED`
- 可用 SSH 私钥：`UNVERIFIED`
- 腾讯云安全组当前规则：`UNVERIFIED`
- 服务器项目路径：`UNVERIFIED`
- 服务器当前 Git commit：`UNVERIFIED`
- 服务器当前 Compose 版本：`UNVERIFIED`
- 证书来源与续期配置：`UNVERIFIED`

在获得服务器控制权之前，本指南只作为操作参考，不表示任何生产状态已被修复。
