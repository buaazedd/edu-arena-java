#!/bin/bash
#cd /Users/trentzhao/Documents/edu-arena-java ./deploy.sh
set -e

PASS="Bnuwlz123"
SERVER="root@8.219.130.23"
REMOTE_DIR="/opt/edu_arena"

# 共用 ssh 选项：仅禁用 host 校验 + 连接超时
# 注意：跨境长肥管道（RTT ~200ms）下，
#   1) 不要加 -O（强制老 SCP 单窗口协议），OpenSSH 9+ 默认 SFTP 是异步 pipeline，吞吐高一个数量级
#   2) 不要加 -C（SSH 压缩），JAR 是 zip 已不可压缩，CPU 反而成瓶颈
#   3) 不要加 ServerAlive*（密集探测在丢包时会提前判定连接死亡）
SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=15"

echo "===== Step 1/3: 本地构建 ====="
mvn clean package -DskipTests

echo "===== Step 2/3: 上传 JAR ====="
# 默认 SCP（OpenSSH 9+ 走 SFTP），跨境上传 55MB 实测 5~10 秒
# 先传到 .new，校验 md5 一致后再原子替换，避免传输中断导致 jar 损坏
upload() {
  sshpass -p "$PASS" scp $SSH_OPTS target/edu-arena-1.0.0.jar "$SERVER:$REMOTE_DIR/edu-arena-1.0.0.jar.new"
}
upload || { echo "[WARN] 第一次上传失败，5 秒后重试一次..."; sleep 5; upload; }

echo "===== Step 2.5/3: 校验并替换 ====="
LOCAL_MD5=$(md5 -q target/edu-arena-1.0.0.jar)
REMOTE_MD5=$(sshpass -p "$PASS" ssh $SSH_OPTS "$SERVER" "md5sum $REMOTE_DIR/edu-arena-1.0.0.jar.new | awk '{print \$1}'")
if [ "$LOCAL_MD5" != "$REMOTE_MD5" ]; then
  echo "[ERROR] MD5 校验失败 local=$LOCAL_MD5 remote=$REMOTE_MD5"; exit 1
fi
echo "MD5 一致：$LOCAL_MD5"
sshpass -p "$PASS" ssh $SSH_OPTS "$SERVER" "mv -f $REMOTE_DIR/edu-arena-1.0.0.jar.new $REMOTE_DIR/edu-arena-1.0.0.jar"

echo "===== Step 3/3: 远程重启 ====="
sshpass -p "$PASS" ssh $SSH_OPTS "$SERVER" "cd $REMOTE_DIR && ./start.sh"

echo "===== 部署完成 ====="
