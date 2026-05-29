FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    # weasyprint 运行依赖: glib(提供gobject)/pango/cairo/gdk-pixbuf + 中文字体
    libglib2.0-0 libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 libharfbuzz0b libfontconfig1 \
    libffi8 shared-mime-info fonts-noto-cjk fonts-noto-color-emoji && \
    rm -rf /var/lib/apt/lists/* && \
    # 让运行时 dlopen('gobject-2.0-0') 能找到 libgobject-2.0.so.0
    ldconfig

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

# 构建阶段冒烟测试: weasyprint 装不上原生库会立即让 build 失败, 避免镜像跑起来才暴露
RUN python -c "from weasyprint import HTML; HTML(string='<p>hi</p>').write_pdf('/tmp/_smoke.pdf'); print('weasyprint OK')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
