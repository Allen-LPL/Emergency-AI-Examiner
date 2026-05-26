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

# FunASR 内置 run_server.sh 用了相对路径调 ./tools/utils/parse_options.sh,
# 必须在 /workspace/FunASR/runtime 目录下执行, 否则会报 No such file or directory.
readonly FUNASR_RUNTIME_DIR="$(dirname "$FUNASR_RUNTIME_SH")"
cd "$FUNASR_RUNTIME_DIR"

echo "[funasr] 启动 ONNX server: $FUNASR_RUNTIME_SH"
echo "[funasr] 工作目录 (必须): $FUNASR_RUNTIME_DIR"
echo "[funasr] 模型下载/缓存目录: $MODEL_DIR"
echo "[funasr] 日志文件: $LOG_FILE"

# nohup + & 让 run_server.sh 后台跑.
# 注意进程模型: bash 包装进程 ($!) 启动 funasr-wss-server (C++ binary) 后会很快退出,
# 真正的 server 是 funasr-wss-server. 之前误把 bash 父进程当成 server 检查存活, 5 秒后必然误判为挂掉,
# 导致脚本 exit 1 + docker 重启 + 日志截断的死循环.
# 用 bash run_server.sh (相对名) 而不是绝对路径, 让内置脚本看到的 $0 与它的 ./tools/utils/... 相对路径预期一致.
nohup bash run_server.sh \
    --download-model-dir "$MODEL_DIR" \
    > "$LOG_FILE" 2>&1 &

bash_pid=$!
echo "[funasr] bash 包装进程 pid=$bash_pid, 等 15 秒让 server binary 启动 + 开始下载模型 ..."
# 等长一点: run_server.sh 内部会先做日志框架初始化, 然后 fork 出 funasr-wss-server,
# 后者会从 modelscope 拉模型 (首启 ~3-5 分钟); 但 15 秒内 binary 进程一定已经 fork 出来了.
sleep 15

# pgrep 真正的 server binary (C++ funasr-wss-server)
server_pid="$(pgrep -f -n funasr-wss-server || true)"
if [[ -z "$server_pid" ]]; then
    echo "[funasr] ERROR: funasr-wss-server 进程未找到, 启动失败. 日志最后 50 行:" >&2
    tail -n 50 "$LOG_FILE" >&2 || true
    exit 1
fi
echo "[funasr] server binary pid=$server_pid, 开始 tail 日志 (server 死时 tail 自动退出, 触发 docker restart) ..."

# tail --pid=$server_pid: server 进程退出时 tail 自动结束 -> 容器 PID 1 退出 -> docker restart 触发.
# 这是 docker 健康监控的正确方式 (前一版用裸 tail -f 在 server 挂掉后会一直 idle, docker 无法感知).
exec tail --pid="$server_pid" -f "$LOG_FILE"
