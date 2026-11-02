# The load harness. Built by Cloud Build (cloudbuild.yaml) via scripts/build-image.sh.
# Same pinning as agent/: digest-pinned bases, dependencies from uv.lock.

FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY src ./src
# Scenario files for `scenarios` (tests 2-6), read by relative path from /app. Tests 3, 5 and 6
# run locally only: their throwaway keys and trail collection need a workstation.
COPY scenarios ./scenarios

FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin harness
WORKDIR /app
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp
USER 10001
ENTRYPOINT ["python", "-m", "agw_harness.cli"]
CMD ["baseline"]
