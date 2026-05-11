#!/bin/bash
#cd /Users/trentzhao/Documents/edu-arena-java ./deploy.sh
set -e

PASS="Bnuwlz123"
SERVER="root@8.219.130.23"
REMOTE_DIR="/opt/edu_arena"

# 共用 ssh 选项：禁用 host 校验 + keepalive（每 15s 一次，连续 4 次失败才断线）
# 网络较慢时（实测上行 ~125KB/s 传 55MB JAR 需要 ~8 分钟），原默认 scp 容易被中间网关掐断
SSH_OPTS="-o StrictHostKeyChecking=no -o ServerAliveInterval=15 -o ServerAliveCountMax=4 -o ConnectTimeout=15"

echo "===== Step 1/3: 本地构建 ====="
mvn clean package -DskipTests

echo "===== Step 2/3: 上传 JAR ====="
# -O 强制走传统 SCP 协议（macOS Ventura+ 默认走 SFTP，对慢链路兼容性更差）
# 上传失败自动重试一次
upload() {
  sshpass -p "$PASS" scp -O $SSH_OPTS target/edu-arena-1.0.0.jar "$SERVER:$REMOTE_DIR/"
}
upload || { echo "[WARN] 第一次上传失败，5 秒后重试一次..."; sleep 5; upload; }

echo "===== Step 3/3: 远程重启 ====="
sshpass -p "$PASS" ssh $SSH_OPTS "$SERVER" "cd $REMOTE_DIR && ./start.sh"

echo "===== 部署完成 ====="
