-- 为 exams 表新增 PDF 报告路径字段
-- 用于 Celery 任务在评分完成后把生成的 PDF 报告绝对路径回写
-- 现有部署执行一次即可; 全新环境会通过 Base.metadata.create_all 自带该列
ALTER TABLE exams ADD COLUMN IF NOT EXISTS report_pdf_url VARCHAR(500);
