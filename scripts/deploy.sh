#!/usr/bin/env bash
# ============================================================================
# 一键部署脚本: 通过 git 把本地分支同步到 192.168.31.82, 并按需重启 docker 服务
#
# 工作流:
#   1) 校验本地工作区干净 (或 -c 自动提交)
#   2) git push 当前分支到 origin (GitHub)
#   3) ssh 远端: git fetch + 强制对齐 origin/<branch> (reset --hard)
#   4) 远端按 ACTION 执行 docker compose: restart / rebuild / recreate
#   5) 可选 -l 跟踪 celery_worker 与 api 日志
#
# 使用方式:
#   ./scripts/deploy.sh                     # 默认 = restart
#   ./scripts/deploy.sh restart             # 适用于 Python 代码改动
#   ./scripts/deploy.sh rebuild             # 适用于改了 Dockerfile / 依赖
#   ./scripts/deploy.sh recreate            # 适用于改了 docker-compose.yml 卷绑定
#   ./scripts/deploy.sh restart -l          # 部署完成后 tail 日志
#   ./scripts/deploy.sh -c "fix: xxx"       # 自动提交未保存改动后再部署
#   ./scripts/deploy.sh --no-push           # 跳过 git push (远端会从 origin 拉到最新已推送提交)
#
# 环境变量:
#   DEPLOY_USER   远端 SSH 用户, 默认 root
#   DEPLOY_HOST   远端主机, 默认 192.168.31.82
#   DEPLOY_DIR    远端代码目录, 默认 /data/sdb/Emergency-AI-Examiner
# ============================================================================

set -euo pipefail

# ---- 基本配置 -----------------------------------------------------------------
REMOTE_HOST="${DEPLOY_HOST:-192.168.31.82}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE_DIR="${DEPLOY_DIR:-/data/sdb/Emergency-AI-Examiner}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

ACTION="restart"
TAIL_LOGS=0
AUTO_COMMIT_MSG=""
DO_PUSH=1

# ---- 参数解析 -----------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    restart|rebuild|recreate)
      ACTION="$1"
      shift
      ;;
    -l|--logs)
      TAIL_LOGS=1
      shift
      ;;
    -c|--commit)
      AUTO_COMMIT_MSG="${2:-}"
      if [[ -z "${AUTO_COMMIT_MSG}" ]]; then
        echo "[deploy] -c/--commit 需要一个 commit 消息参数" >&2
        exit 1
      fi
      shift 2
      ;;
    --no-push)
      DO_PUSH=0
      shift
      ;;
    -h|--help)
      grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
      exit 0
      ;;
    *)
      echo "[deploy] 未知参数: $1" >&2
      echo "[deploy] 用法: ./scripts/deploy.sh [restart|rebuild|recreate] [-l] [-c \"msg\"] [--no-push]" >&2
      exit 1
      ;;
  esac
done

cd "${LOCAL_DIR}"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
ORIGIN_URL="$(git remote get-url origin 2>/dev/null || echo '<未配置 origin>')"

echo "============================================================"
echo "[deploy] 本地目录  : ${LOCAL_DIR}"
echo "[deploy] 当前分支  : ${BRANCH}"
echo "[deploy] origin    : ${ORIGIN_URL}"
echo "[deploy] 远端目标  : ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
echo "[deploy] docker 动作: ${ACTION}"
echo "[deploy] 跟踪日志  : $([ ${TAIL_LOGS} -eq 1 ] && echo '是' || echo '否')"
echo "============================================================"

# ---- 1) 本地工作区检查 / 自动提交 ----------------------------------------------
if [[ -n "$(git status --porcelain)" ]]; then
  if [[ -n "${AUTO_COMMIT_MSG}" ]]; then
    echo "[deploy] [1/4] 检测到未提交改动, 按 -c 参数自动提交..."
    git add -A
    git commit -m "${AUTO_COMMIT_MSG}"
  else
    echo "[deploy] 本地工作区有未提交改动, 拒绝部署:" >&2
    git status --short >&2
    echo "" >&2
    echo "[deploy] 请先手动 git commit, 或使用 -c \"提交消息\" 自动提交" >&2
    exit 1
  fi
else
  echo "[deploy] [1/4] 本地工作区干净"
fi

# ---- 2) 推送到 origin ---------------------------------------------------------
if [[ ${DO_PUSH} -eq 1 ]]; then
  echo "[deploy] [2/4] 推送 ${BRANCH} -> origin..."
  git push origin "${BRANCH}"
else
  echo "[deploy] [2/4] 跳过 git push (--no-push)"
fi

LOCAL_HEAD="$(git rev-parse HEAD)"
echo "[deploy] 本地 HEAD: ${LOCAL_HEAD}"

# ---- 3) 远端 git 拉取 + docker 操作 -------------------------------------------
# 远端用 fetch + reset --hard 强制对齐 origin/<branch>, 避免远端有本地修改时 pull 冲突.
# 远端运行时数据 (uploads/outputs/logs/models/.env) 已在 .gitignore, 不会被 git 覆盖.
# 通过 ssh stdin 把脚本传给远端 bash, 用环境变量传参, 避免本地 heredoc 与命令替换嵌套打架.
echo "[deploy] [3/4] 远端 git 同步并执行 docker 动作: ${ACTION}"

ssh "${REMOTE_USER}@${REMOTE_HOST}" \
  "REMOTE_DIR='${REMOTE_DIR}' BRANCH='${BRANCH}' ACTION='${ACTION}' bash -s" <<'REMOTE_EOF'
set -euo pipefail

cd "${REMOTE_DIR}"

echo "[remote] git fetch --prune origin"
git fetch --prune origin

echo "[remote] 切到分支 ${BRANCH} 并强制对齐 origin/${BRANCH}"
git checkout -B "${BRANCH}" "origin/${BRANCH}"
git reset --hard "origin/${BRANCH}"
echo "[remote] 远端 HEAD: $(git rev-parse HEAD)"

# 确保宿主机绑定挂载源目录存在 (首次必要, 后续幂等无害)
mkdir -p uploads outputs logs

case "${ACTION}" in
  restart)
    echo "[remote] docker compose restart api celery_worker"
    docker compose restart api celery_worker
    ;;
  rebuild)
    echo "[remote] docker compose up -d --build api celery_worker"
    docker compose up -d --build api celery_worker
    ;;
  recreate)
    echo "[remote] docker compose down && docker compose up -d (保留 db_data/redis_data/model_cache)"
    docker compose down
    docker compose up -d
    ;;
esac

echo "[remote] docker compose ps:"
docker compose ps
REMOTE_EOF

# ---- 4) 可选 tail 日志 --------------------------------------------------------
echo "[deploy] [4/4] 部署完成"

if [[ ${TAIL_LOGS} -eq 1 ]]; then
  echo "[deploy] 跟踪 celery_worker / api 日志 (Ctrl+C 退出)..."
  ssh -t "${REMOTE_USER}@${REMOTE_HOST}" \
    "cd ${REMOTE_DIR} && docker compose logs -f --tail=100 celery_worker api"
fi
