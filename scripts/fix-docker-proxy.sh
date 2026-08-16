#!/usr/bin/env bash
# 关闭 Docker daemon 的 Clash 代理，改用国内镜像拉取镜像
set -euo pipefail

DROPIN_DIR=/etc/systemd/system/docker.service.d
DAEMON_JSON=/etc/docker/daemon.json

echo "==> 备份并禁用 docker 代理 drop-in"
sudo mkdir -p "$DROPIN_DIR"
for f in http-proxy.conf proxy.conf; do
  if [[ -f "$DROPIN_DIR/$f" ]]; then
    sudo mv "$DROPIN_DIR/$f" "$DROPIN_DIR/$f.bak.$(date +%Y%m%d%H%M%S)"
    echo "    moved $f -> $f.bak.*"
  fi
done

echo "==> 确保 registry-mirrors 已配置"
if [[ ! -f "$DAEMON_JSON" ]] || ! grep -q 'registry-mirrors' "$DAEMON_JSON" 2>/dev/null; then
  sudo tee "$DAEMON_JSON" >/dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ]
}
EOF
  echo "    wrote $DAEMON_JSON"
else
  echo "    $DAEMON_JSON 已有 mirrors，跳过"
fi

echo "==> 重启 docker"
sudo systemctl daemon-reload
sudo systemctl restart docker
sleep 2

echo "==> 当前代理 / 镜像配置"
docker info 2>/dev/null | grep -iE 'HTTP Proxy|HTTPS Proxy|No Proxy|Registry Mirrors' -A2 || true

echo "==> 测试拉取 redis:latest"
docker pull redis:latest

echo "==> 完成"
