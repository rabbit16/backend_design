# 国内加速：基础镜像默认走 DaoCloud DockerHub 代理；可用 --build-arg 覆盖
ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.11-slim
FROM ${PYTHON_BASE_IMAGE} AS runtime

# apt / pip 镜像（默认中科大；可改为 mirrors.aliyun.com、mirrors.tuna.tsinghua.edu.cn 等）
ARG APT_MIRROR=mirrors.ustc.edu.cn
ARG PIP_INDEX_URL=https://mirrors.ustc.edu.cn/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.ustc.edu.cn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /app

# Debian apt → 国内源（bookworm 用 debian.sources；旧版用 sources.list）
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g; s|security.debian.org|${APT_MIRROR}|g" \
        /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts
COPY src ./src

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${PORT:-8000}/api/v1/health || exit 1

CMD ["sh", "-c", "python scripts/db_migrate.py upgrade && uvicorn src.app.main:create_app --factory --host ${HOST:-0.0.0.0} --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
