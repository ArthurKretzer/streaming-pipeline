FROM arthurkretzer/spark:3.5.4

USER root

COPY --from=ghcr.io/astral-sh/uv:0.5.21 /uv /uvx /bin/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHON_VERSION=3.13
ENV WORK_DIR=/app

# Create directories
RUN mkdir -p ${WORK_DIR}
WORKDIR ${WORK_DIR}

# Install Python
RUN uv python install ${PYTHON_VERSION} --default --preview

# Copy project files
COPY . /app

# Install dependencies as root
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --group consumer --no-dev

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --group consumer --no-dev

# Fix permissions after installation
RUN chown -R spark:spark ${WORK_DIR}

ENV PATH="${WORK_DIR}/.venv/bin:$PATH"

# Switch to spark user at the end
USER spark
