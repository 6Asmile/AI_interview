# ai-interview-backend/Dockerfile

# 使用官方的 Python 3.12 slim 镜像作为基础
FROM python:3.12-slim

# 设置容器内的工作目录
WORKDIR /app

# 设置两个推荐的环境变量
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- 【核心修复】---
# 安装编译 mysqlclient 所需的、最精确的系统依赖包
# build-essential: 提供了 gcc, make 等基础编译工具
# pkg-config: 用于帮助编译系统找到其他库的工具
# libmariadb-dev: MariaDB 的客户端C语言开发库，mysqlclient 会优先使用它
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*
# --- 修复结束 ---

# 安装 gunicorn
RUN pip install gunicorn

# 复制依赖文件到容器中
COPY requirements.txt .

# 现在，系统依赖已就绪，可以成功安装所有 Python 包了
RUN pip install --no-cache-dir -r requirements.txt

# 将后端项目的全部代码复制到容器的 /app 目录中
COPY . .

# 【核心新增】在容器构建时，运行 collectstatic 命令
# 这会找到所有 app (包括 admin, simpleui) 的静态文件，
# 并将它们复制到 settings.py 中定义的 STATIC_ROOT (即 /app/staticfiles) 目录
RUN python manage.py collectstatic --noinput