"""Agent worker entrypoint (docs/BACKEND_BUILD_STEPS.md Step 45) — runs
every Python consumer this project has built as one process: Scraper,
Retriever, Scoring, Generator, Filler+Verifier. One process, not one
container per agent, keeps the demo docker-compose topology small; each
consumer is still an independent bus.Consumer loop underneath, exactly
as tested in isolation throughout every earlier step.

Falls back to deterministic demo_clients when no real LLM/embedding API
key is configured (ANTHROPIC_API_KEY / OPENAI_API_KEY) — a cold `make up`
with no cloud credentials still runs the full pipeline end to end,
honestly logged as demo mode rather than silently pretending to call a
real model.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

import asyncpg
import httpx
import redis.asyncio as redis
from minio import Minio
from playwright.async_api import Browser, async_playwright

from agentos_agents.common.consumer import Consumer
from agentos_agents.common.llm_client import AnthropicLLMClient
from agentos_agents.demo_clients import (
    DemoDomAnalysisLLMClient,
    DemoEmbeddingClient,
    DemoGeneratorLLMClient,
    DemoScoringLLMClient,
)
from agentos_agents.filler.agent import FillerVerifierConsumer
from agentos_agents.filler.verify import PolicyCallbackClient
from agentos_agents.generator.agent import GeneratorConsumer
from agentos_agents.generator.storage import MinioStorageClient
from agentos_agents.retriever.agent import RetrieverConsumer
from agentos_agents.retriever.embedding import OpenAIEmbeddingClient
from agentos_agents.scoring.agent import ScoringConsumer
from agentos_agents.scraper.agent import DEFAULT_ATS_ALLOWLIST, ScraperConsumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agentos_agents.worker")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _build_consumers(
    redis_client: redis.Redis,
    pg_pool: asyncpg.Pool,
    http_client: httpx.AsyncClient,
    storage_client: MinioStorageClient,
    browser: Browser,
    consumer_name: str,
) -> list[Consumer]:
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    demo_mode = not (anthropic_key and openai_key)
    if demo_mode:
        logger.warning(
            "no ANTHROPIC_API_KEY/OPENAI_API_KEY configured — running with "
            "deterministic demo LLM/embedding clients, not a real model"
        )
        embedding_client = DemoEmbeddingClient()
        scoring_llm = DemoScoringLLMClient()
        generator_llm = DemoGeneratorLLMClient()
        dom_analysis_llm = DemoDomAnalysisLLMClient()
    else:
        embedding_client = OpenAIEmbeddingClient(http_client, openai_key)
        scoring_llm = AnthropicLLMClient(http_client, anthropic_key)
        generator_llm = AnthropicLLMClient(http_client, anthropic_key)
        dom_analysis_llm = AnthropicLLMClient(http_client, anthropic_key)

    allow_insecure_local_targets = (
        _env("SCRAPER_ALLOW_INSECURE_LOCAL_TARGETS", "false").lower() == "true"
    )
    extra_allowlist = [
        d.strip() for d in _env("SCRAPER_EXTRA_ALLOWLIST", "").split(",") if d.strip()
    ]
    allowlist = DEFAULT_ATS_ALLOWLIST + extra_allowlist

    policy_client = PolicyCallbackClient(
        http_client,
        _env("INTERNAL_API_BASE_URL", "http://localhost:8080"),
        _env("INTERNAL_SHARED_SECRET", "dev-internal-secret"),
    )

    return [
        ScraperConsumer(
            redis_client,
            pg_pool,
            "scraper-group",
            consumer_name,
            http_client,
            allowlist=allowlist,
            allow_insecure_local_targets=allow_insecure_local_targets,
        ),
        RetrieverConsumer(
            redis_client, pg_pool, "retriever-group", consumer_name, embedding_client
        ),
        ScoringConsumer(redis_client, pg_pool, "scoring-group", consumer_name, scoring_llm),
        GeneratorConsumer(
            redis_client, pg_pool, "generator-group", consumer_name, generator_llm, storage_client
        ),
        FillerVerifierConsumer(
            redis_client,
            pg_pool,
            "filler-group",
            consumer_name,
            browser,
            dom_analysis_llm,
            policy_client,
        ),
    ]


async def main() -> None:
    database_url = _env(
        "DATABASE_URL", "postgresql://agentos:agentos_dev@localhost:5432/agentos"
    )
    redis_addr = _env("REDIS_ADDR", "localhost:6379")
    redis_host, _, redis_port = redis_addr.partition(":")

    pg_pool = await asyncpg.create_pool(database_url)
    redis_client = redis.Redis(
        host=redis_host, port=int(redis_port or 6379), decode_responses=True
    )
    http_client = httpx.AsyncClient()

    minio_client = Minio(
        _env("MINIO_ENDPOINT", "localhost:9000"),
        access_key=_env("MINIO_ACCESS_KEY", "agentos"),
        secret_key=_env("MINIO_SECRET_KEY", "agentos_dev_pw"),
        secure=False,
    )
    storage_client = MinioStorageClient(minio_client)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)

    consumer_name = _env("WORKER_ID", "worker-1")
    consumers = _build_consumers(
        redis_client, pg_pool, http_client, storage_client, browser, consumer_name
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    async def watch_and_stop() -> None:
        await stop_event.wait()
        logger.info("shutdown signal received, stopping consumers")
        for c in consumers:
            c.stop()

    logger.info(
        "agent worker starting",
        extra={"consumers": [type(c).__name__ for c in consumers]},
    )
    try:
        await asyncio.gather(watch_and_stop(), *[c.run() for c in consumers])
    finally:
        await browser.close()
        await playwright.stop()
        await http_client.aclose()
        await redis_client.aclose()
        await pg_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
