# AgentHub Production Checklist

## DNS

- [ ] 确认 `synplex.xyz` A 记录指向生产服务器公网 IP
- [ ] 确认域名可被公网 DNS 解析
- [ ] 确认子域名/裸域名策略

## TLS

- [ ] 配置 cert-manager 或手动上传证书
- [ ] 开启 HTTP → HTTPS redirect
- [ ] 确认 TLSv1.2/TLSv1.3
- [ ] 配置自动续期

## Firewall

- [ ] 仅开放 80/443
- [ ] 不开放 PostgreSQL/Redis/Grafana/Prometheus/Jaeger
- [ ] 限制 SSH 来源
- [ ] 检查云安全组

## Secrets

- [ ] `.env` 不进入 Git
- [ ] 使用 External Secrets 或云 Secret Manager
- [ ] 强随机 JWT_SECRET_KEY
- [ ] 生产 SMTP/LLM key 隔离

## Database

- [ ] PostgreSQL 使用持久卷
- [ ] 配置备份
- [ ] 配置恢复演练
- [ ] 限制公网访问

## Redis

- [ ] 使用持久卷或明确无持久化策略
- [ ] 限制公网访问
- [ ] 配置内存上限和淘汰策略

## Backup / Restore

- [ ] 定期备份 PostgreSQL
- [ ] 定期备份 Redis 如需要
- [ ] 备份检查点/LangGraph checkpoints
- [ ] 恢复演练
- [ ] 记录 RPO/RTO

## Docker

- [ ] `restart: unless-stopped`
- [ ] healthcheck
- [ ] 镜像版本固定，不使用 `latest`
- [ ] 日志轮转

## Nginx

- [ ] 前端静态文件
- [ ] `/api` 代理
- [ ] SSE 不超时/不缓冲
- [ ] WebSocket upgrade
- [ ] request body size 限制
- [ ] X-Forwarded-For 正确传递

## LLM / Fallback

- [ ] primary model 可用
- [ ] fallback model 可用
- [ ] 真实 fallback E2E
- [ ] token/cost 记录

## Celery

- [ ] worker 健康
- [ ] retry 策略验证
- [ ] stale execution 清理
- [ ] DLQ 可查看

## Monitoring

- [ ] Prometheus targets up
- [ ] Grafana dashboard
- [ ] Alert rules

## Logging / Tracing

- [ ] OTLP 日志
- [ ] Jaeger trace
- [ ] request/execution correlation

## Email

- [ ] Resend/SMTP 配置
- [ ] SPF/DKIM/DMARC
- [ ] 验证码邮件真实发送

## Healthcheck

- [ ] `/health` 返回 `ok`
- [ ] DB/Redis/LLM 均健康

## Rollback

- [ ] 镜像 tag 可回滚
- [ ] DB migration 可回滚
- [ ] 静态前端可回滚
