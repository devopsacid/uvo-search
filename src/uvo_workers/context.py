"""Process boilerplate shared by every long-lived worker.

``WorkerContext`` is an async context manager that owns, in order: client
creation, Redis connect-or-exit, the ``worker_started`` event, SIGTERM/SIGINT
handling, the health server, and - on the way out - the health task,
``worker_stopped`` event and client shutdown.
"""

import asyncio
import logging
import signal
import time
import uuid
from collections.abc import Callable

from redis.asyncio import Redis

from uvo_core.adapters.mongo.ingestion_log import log_event
from uvo_core.adapters.redis.client import RedisSettings, get_redis_settings
from uvo_workers.clients import WorkerClients, open_mongo, open_neo4j, open_redis
from uvo_workers.errors import redact_exception
from uvo_workers.health import serve_health
from uvo_workers.metrics import WorkerMetricsCollector, build_registry

logger = logging.getLogger(__name__)


class WorkerContext:
    """``async with WorkerContext(...) as ctx`` yields the running process state.

    ``ctx.metrics`` is the live dict served by the health endpoint; callers
    seed their own keys via ``metrics`` and mutate it afterwards.
    """

    def __init__(
        self,
        *,
        name: str,
        component: str,
        registry_name: str,
        start_message: str,
        stop_message: str,
        health_port: int,
        metrics: dict | None = None,
        source: str | None = None,
        start_details: dict | None = None,
        stop_details: Callable[[], dict] | None = None,
        redis_settings: RedisSettings | None = None,
        clients: WorkerClients | None = None,
        with_neo4j: bool = False,
        instance_id: str | None = None,
    ) -> None:
        self.name = name
        self.component = component
        self.source = source
        self.instance_id = instance_id or uuid.uuid4().hex
        # Adopt the caller's dict (not a copy): callers keep mutating it.
        self.metrics: dict = metrics if metrics is not None else {}
        self.metrics["instance_id"] = self.instance_id
        self.metrics["redis_connected"] = False
        self.metrics["started_at_ts"] = time.time()
        self.stop_event = asyncio.Event()
        self._registry_name = registry_name
        self._health_port = health_port
        self._start_message = start_message
        self._stop_message = stop_message
        self._start_details = start_details
        self._stop_details = stop_details
        self._redis_settings = redis_settings
        self._with_neo4j = with_neo4j
        self.clients: WorkerClients | None = clients
        self._health_task: asyncio.Task | None = None

    @property
    def db(self):
        return self.clients.db

    @property
    def redis(self) -> Redis:
        return self.clients.redis

    @property
    def neo4j(self):
        return self.clients.neo4j

    def build_collector(self) -> WorkerMetricsCollector:
        """Prometheus collector for this process, labelled with its source/instance."""
        return build_registry(self._registry_name, source=self.source, instance_id=self.instance_id)

    async def __aenter__(self) -> "WorkerContext":
        if self.clients is None:
            mongo, db = open_mongo()
            self.clients = WorkerClients(mongo=mongo, db=db)
        await self._connect_redis_or_exit()
        if self._with_neo4j and self.clients.neo4j is None:
            self.clients.neo4j = open_neo4j()

        await log_event(
            self.db,
            level="info",
            event="worker_started",
            component=self.component,
            source=self.source,
            instance_id=self.instance_id,
            message=self._start_message,
            details=self._start_details,
        )
        self._install_signal_handlers()
        if self._health_port:
            self._health_task = asyncio.create_task(
                serve_health(
                    self._health_port,
                    lambda: dict(self.metrics),
                    registry=self.build_collector(),
                ),
                name=f"health-{self.name}",
            )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            try:
                await self._health_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await log_event(
                self.db,
                level="info",
                event="worker_stopped",
                component=self.component,
                source=self.source,
                instance_id=self.instance_id,
                message=self._stop_message,
                details=self._stop_details() if self._stop_details else None,
            )
        except Exception:
            pass
        await self.clients.close()
        logger.info("%s: worker stopped", self.name)

    async def _connect_redis_or_exit(self) -> None:
        try:
            if self.clients.redis is None:
                self.clients.redis = await open_redis(self._redis_settings or get_redis_settings())
            await self.clients.redis.ping()
            self.metrics["redis_connected"] = True
        except Exception as exc:
            logger.critical("Redis connection failed for %s: %s", self.name, exc)
            try:
                await log_event(
                    self.db,
                    level="critical",
                    event="redis_connect_failed",
                    component=self.component,
                    source=self.source,
                    instance_id=self.instance_id,
                    message=redact_exception(exc),
                )
            except Exception:
                pass
            self.clients.mongo.close()
            raise SystemExit(1) from exc

    def _install_signal_handlers(self) -> None:
        def _on_signal() -> None:
            logger.info("Shutdown signal received, stopping %s", self.name)
            self.stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except (NotImplementedError, RuntimeError):
                pass
