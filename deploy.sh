#!/bin/bash
#cd /Users/trentzhao/Documents/edu-arena-java ./deploy.sh
set -e

PASS="Bnuwlz123"
SERVER="root@8.219.130.23"
REMOTE_DIR="/opt/edu_arena"

echo "===== Step 1/3: 本地构建 ====="
mvn clean package -DskipTests

echo "===== Step 2/3: 上传 JAR ====="
sshpass -p "$PASS" scp -o StrictHostKeyChecking=no target/edu-arena-1.0.0.jar "$SERVER:$REMOTE_DIR/"

echo "===== Step 3/3: 远程重启 ====="
sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$SERVER" "cd $REMOTE_DIR && ./start.sh"

echo "===== 部署完成 ====="
