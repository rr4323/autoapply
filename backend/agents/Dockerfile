# Python agent-worker image (docs/BACKEND_BUILD_STEPS.md Step 45). Needs
# a real Chromium for the Filler/Verifier Agents (Step 41/43) — --with-deps
# works here (root, full apt access) unlike some sandboxed dev shells
# that lack sudo, which is exactly why that install had to be deferred to
# CI/this image rather than assumed available everywhere.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
# --no-install-project (nothing to install yet — only pyproject.toml/
# uv.lock exist in this layer) leaves `uv run` unable to build this
# project's own package, which it otherwise insists on doing; --no-project
# on the playwright install itself sidesteps that entirely (playwright
# the *dependency* is already synced — this step only needs its browser
# binary, not this project's source).
RUN uv sync --frozen --no-install-project
RUN uv run --no-project playwright install --with-deps chromium

COPY . .
RUN uv sync --frozen

ENTRYPOINT ["uv", "run", "python", "-m", "agentos_agents.worker"]
