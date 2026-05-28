#!/usr/bin/env bash
# ============================================================================
# 数据库重置脚本 - 删除所有业务表, 让后端启动时自动重建
#
# 适用场景: 表结构破坏性变更 (本次设备直连改造 = 用此脚本)
# 不动: db_data 卷本身、postgres 用户/角色
#
# 使用方式:
#   ./scripts/reset_db.sh              # 在本机 docker 上执行 (本地开发)
#   REMOTE=1 ./scripts/reset_db.sh     # ssh 192.168.31.82 上执行
#
# 环境变量:
#   DEPLOY_HOST  远端主机, 默认 192.168.31.82
#   DEPLOY_USER  远端 SSH 用户, 默认 root
#   DEPLOY_DIR   远端代码目录, 默认 /data/sdb/Emergency-AI-Examiner
# ============================================================================

set -euo pipefail

REMOTE="${REMOTE:-0}"
REMOTE_HOST="${DEPLOY_HOST:-192.168.31.82}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_DIR="${DEPLOY_DIR:-/data/sdb/Emergency-AI-Examiner}"

# 注意删除顺序: 先删带外键的子表, 再删主表
SQL=$(cat <<'EOF'
DROP TABLE IF EXISTS exam_scores CASCADE;
DROP TABLE IF EXISTS exam_events CASCADE;
DROP TABLE IF EXISTS speaker_role_maps CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE;
DROP TABLE IF EXISTS cpr_metrics CASCADE;
DROP TABLE IF EXISTS sensor_data CASCADE;
DROP TABLE IF EXISTS exams CASCADE;
DROP TABLE IF EXISTS users CASCADE;
EOF
)

echo "==> 将执行以下 SQL:"
echo "${SQL}"
echo

if [[ "${REMOTE}" == "1" ]]; then
  echo "==> 在远端 ${REMOTE_USER}@${REMOTE_HOST} 上执行..."
  ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DIR} && docker exec -i examiner_db psql -U postgres -d emergency_examiner" <<< "${SQL}"
else
  echo "==> 在本地 docker 上执行..."
  docker exec -i examiner_db psql -U postgres -d emergency_examiner <<< "${SQL}"
fi

echo "==> 数据库已重置, 重启后端会自动重建新表结构"
