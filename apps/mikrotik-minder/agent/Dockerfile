# syntax=docker/dockerfile:1.7
# Build the agent into a venv, then copy it into a slim runtime image.

ARG PY_VERSION=3.13

FROM python:${PY_VERSION}-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /opt/minder \
    && /opt/minder/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/minder/bin/pip install --no-cache-dir .


FROM python:${PY_VERSION}-slim

# git for the export repo; openssh-client so GIT_SSH_COMMAND can reach a remote;
# tini so SIGTERM from kubelet actually terminates Python promptly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         git \
         openssh-client \
         ca-certificates \
         tini \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 minder \
    && useradd  --system --uid 1000 --gid 1000 \
                --home-dir /var/lib/mikrotik-minder \
                --shell /usr/sbin/nologin minder \
    && install -d -m 0700 -o 1000 -g 1000 /var/lib/mikrotik-minder/.ssh \
    && install -d -m 0750 -o 1000 -g 1000 /var/lib/mikrotik-minder/configs \
    && install -d -m 0750 -o 1000 -g 1000 /var/lib/mikrotik-minder/backups

COPY --from=builder /opt/minder /opt/minder
ENV PATH=/opt/minder/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/var/lib/mikrotik-minder

USER 1000:1000
WORKDIR /var/lib/mikrotik-minder

# Healthcheck: parsing --help is enough to confirm the entrypoint runs.
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
    CMD mikrotik-minder-agent --help >/dev/null || exit 1

ENTRYPOINT ["tini", "--", "mikrotik-minder-agent"]
CMD ["run", "--config", "/etc/mikrotik-minder/config.yaml", "-v"]
