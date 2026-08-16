# Phase 5.7 Security Hardening

## Changes

- Removed public `8080` port.
- Published `80:80` for frontend.
- Nginx port 80 now returns `301` to HTTPS.
- Port `443` remains public and serves HTTPS.

## Verification

### Final public listening ports

```text
0.0.0.0:22   SSH
0.0.0.0:80   HTTP
0.0.0.0:443  HTTPS
```

All other services bind `127.0.0.1`.

### HTTP / HTTPS

```text
http://synplex.xyz  -> 301 Moved Permanently
https://synplex.xyz -> 200 OK
```

### Backend health

```text
{"status":"ok","database":true,"redis":true,"llm":true}
```

## Remaining

- Tencent Cloud security group still needs to close previously exposed ports at cloud firewall layer.
- Real two-model fallback still unverified.
- PostgreSQL backup/restore drill still unverified.
