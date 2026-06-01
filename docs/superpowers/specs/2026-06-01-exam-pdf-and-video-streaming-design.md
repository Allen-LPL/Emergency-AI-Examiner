# 考试报告 PDF 持久化 与 原始视频流式播放接口 — 设计文档

- 日期：2026-06-01
- 涉及目录：`backend/app/`、`scripts/`
- 不涉及：`ai_engine/pipeline.py`（pipeline 保持纯 AI 处理职责）

## 1. 背景与目标

当前评分流程只在请求 `GET /exam/{exam_id}/report/pdf` 时按需渲染 PDF，无落盘、无入库。
本次改造希望：

1. AI 流水线处理完成（即 Celery 任务里 `pipeline.process()` 返回之后），自动生成
   PDF 报告，落到 `outputs/exam_{exam_id}_report.pdf`，并把绝对路径写入
   `exams.report_pdf_url`，方便后续直接下载/分发，避免每次重新渲染。
2. 新增一个能在常规 H5 浏览器中直接 `<video>` 播放（支持拖动进度条）的接口，
   按 `exams.video_url`（原始上传视频）的路径提供 HTTP Range 流式响应，
   区别于现有返回 AI 标注视频的 `/exam/{exam_id}/video`。

## 2. 数据库变更

### 2.1 模型新增字段

`backend/app/models/exam.py` 在 `processed_video_url` 旁新增：

```python
# AI 生成的 PDF 评分报告路径(绝对路径)
report_pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

### 2.2 迁移脚本

后端 `lifespan` 用的是 `Base.metadata.create_all`，只会建表，不会为已存在表加列。
新增脚本 `scripts/migrate_add_report_pdf_url.sql`：

```sql
ALTER TABLE exams ADD COLUMN IF NOT EXISTS report_pdf_url VARCHAR(500);
```

部署到远端 `192.168.31.82:/data/sdb/Emergency-AI-Examiner` 时手动执行一次；
全新环境会通过 `metadata.create_all` 自带该列。

## 3. PDF 生成（Celery 任务）

修改 `backend/app/tasks/exam_task.py`，在 `save_exam_scores_sync(...)` 之后、
`exam.status = "completed"` 之前插入"生成 PDF 报告"段落：

- 调 `report_service.generate_pdf_report(exam_id, score_result=result["scores"],
  created_at=str(exam.created_at))`。
  - `score_result` 是 `pipeline.process()` 返回的 dict；
    `_normalize_score_result` 已经兼容 dict 形态。
- 写到 `Path(settings.output_dir).resolve() / f"exam_{exam_id}_report.pdf"`。
- 把绝对路径赋给 `exam.report_pdf_url`。
- 整段用 try/except 包裹，失败仅记录 `logger.exception`（与标注视频生成同策略：
  副产物失败不阻塞主流程）。

## 4. 原始视频播放接口（HTTP Range）

新增 `GET /exam/{exam_id}/video/play`，位于 `backend/app/api/v1/exam.py`，
区别于现有 `/exam/{exam_id}/video`（后者返回 AI 标注视频）。

### 4.1 路径解析

- 取 `exam.video_url`：绝对路径直接用，相对路径相对 `settings.upload_dir` 解析。
- 文件不存在 → 404。

### 4.2 Content-Type 推断

按扩展名映射：

| 扩展名 | Content-Type |
| --- | --- |
| `.mp4` | `video/mp4` |
| `.webm` | `video/webm` |
| `.mov` | `video/quicktime` |
| `.mkv` | `video/x-matroska` |
| `.avi` | `video/x-msvideo` |
| 其他 | `application/octet-stream` |

### 4.3 Range 解析与响应

- 解析请求头 `Range: bytes=start-end`，end 缺省时取 `file_size-1`。
- 没 Range：
  - 200
  - `Accept-Ranges: bytes`
  - `Content-Length: file_size`
- 有 Range：
  - 206 Partial Content
  - `Accept-Ranges: bytes`
  - `Content-Range: bytes start-end/file_size`
  - `Content-Length: end-start+1`
- 非法 Range（start ≥ file_size、start > end 等）→ 416 Range Not Satisfiable，
  带 `Content-Range: bytes */file_size`。

### 4.4 流式输出

- 用 `StreamingResponse` + 文件指针 `seek(start)` + 64KB chunk 读取，
  避免一次性把整段视频读到内存。
- `Content-Disposition: inline`（浏览器播放而非下载）。
- `Cache-Control: no-cache`（考试视频不被中间代理缓存）。

## 5. 影响面

- `pipeline.py` 不动。
- `frontend` 不动；前端如需播放原始视频，把现有调用从 `/video` 换到 `/video/play` 即可
  （或并存：`/video` 给标注视频、`/video/play` 给原始视频）。
- 部署需在远端数据库人工执行 `scripts/migrate_add_report_pdf_url.sql` 一次。

## 6. 风险与回退

- PDF 生成 try/except 包裹，依赖（weasyprint）故障不影响评分流程。
- Range 解析以 RFC 7233 单 range 形式为准，不支持 multipart range（浏览器
  `<video>` 标签实测不会发 multipart range，足够）。
- 回退：删除字段（`DROP COLUMN report_pdf_url`）+ 回滚 Celery 任务/路由变更即可，
  历史 PDF 文件随保留即可（不影响其它流程）。
