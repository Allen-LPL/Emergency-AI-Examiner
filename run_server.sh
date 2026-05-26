#!/usr/bin/env bash
# FunASR offline ASR server 启动脚本.
#
# 由 docker-compose 的 funasr 服务通过 volume mount 调用 (宿主路径 ./run_server.sh,
# 容器内路径 /start_funasr.sh, 避免和镜像内置的 /workspace/FunASR/runtime/run_server.sh 重名).
#
# 作用:
#   1. 后台启动 FunASR 镜像内置的 run_server.sh, 默认使用 ONNX 版 Paraformer-large + VAD + 标点 + ITN + LM;
#   2. 把 stdout/stderr 重定向到 /workspace/funasr_server.log 便于排查;
#   3. 用 tail -f 让容器 PID 1 保持前台 (否则 nohup 子进程 detach 后容器会立即退出).
#
# 历史踩坑:
#   - YAML `>` 折叠 + bash 反斜杠续行不兼容, 直接在 compose 里写 inline command 会出现
#     `--download-model-dir: command not found`; 用外部脚本就没这个问题, 反斜杠续行正常工作.
#   - 模型 mount 到 /workspace/models, 第一次启动从 modelscope 下载到这, 后续启动直接复用.
#   - 之前那个跑了 5 天的容器其实 server 没启 (只是 stdin/tty 让壳活着), 这套脚本能保证 server 真的起来.

set -euo pipefail

readonly FUNASR_RUNTIME_SH="/workspace/FunASR/runtime/run_server.sh"
readonly MODEL_DIR="/workspace/models"
readonly LOG_FILE="/workspace/funasr_server.log"

# 兜底检查: docker-compose 把 /data/sdb/funasr-runtime-resources/ mount 到 /workspace/
# 会覆盖镜像内置目录, 如果宿主机这个目录里没有 FunASR/ 子目录, 镜像内置的 run_server.sh 就找不到了.
if [[ ! -f "$FUNASR_RUNTIME_SH" ]]; then
    echo "[funasr] ERROR: 找不到 $FUNASR_RUNTIME_SH" >&2
    echo "[funasr] 可能原因: docker-compose volumes 里 /workspace 的 mount 覆盖了镜像内置 FunASR 目录." >&2
    echo "[funasr] 修复: 让宿主机 /data/sdb/funasr-runtime-resources/ 里包含 FunASR/ 子目录," >&2
    echo "[funasr]       或者改 mount 只挂 models 子目录, 不要覆盖整个 /workspace." >&2
    exit 1
fi

mkdir -p "$MODEL_DIR"

echo "[funasr] 启动 ONNX server: $FUNASR_RUNTIME_SH"
echo "[funasr] 模型下载/缓存目录: $MODEL_DIR"
echo "[funasr] 日志文件: $LOG_FILE"

# nohup + & 让 server 后台跑, 当前 shell 立即返回去 tail 日志
nohup bash "$FUNASR_RUNTIME_SH" \
    --download-model-dir "$MODEL_DIR" \
    > "$LOG_FILE" 2>&1 &

server_pid=$!
echo "[funasr] server pid=$server_pid, 等 5 秒后开始 tail 日志 ..."
sleep 5

# 如果 server 已经死了 (启动失败), 直接报错退出, 让容器 restart 策略生效
if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "[funasr] ERROR: server 进程 $server_pid 已退出, 启动失败. 日志最后 30 行:" >&2
    tail -n 30 "$LOG_FILE" >&2 || true
    exit 1
fi

# tail -f 让容器 PID 1 保持前台; server 挂掉时 tail 仍在跑,
# 配合 docker-compose 的 restart: unless-stopped 由外层 docker 监控容器整体存活
exec tail -f "$LOG_FILE"
