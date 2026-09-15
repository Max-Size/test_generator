"""Логирование и замер времени этапов обработки запроса.

Каждому запросу присваивается короткий id (rid), который проставляется во все
строки лога — так виден весь путь запроса: извлечение текста → сборка контекста →
вызовы LLM → валидация → ответ.
"""
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from .config import settings

_rid: ContextVar[str] = ContextVar("rid", default="-")


class _RidFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = _rid.get()
        return True


def setup_logging() -> None:
    """Настроить формат и уровень. Вызывается один раз при старте приложения."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(rid)s] %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    handler.addFilter(_RidFilter())

    root = logging.getLogger("test_generator")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False


def new_request_id() -> str:
    rid = uuid.uuid4().hex[:8]
    _rid.set(rid)
    return rid


log = logging.getLogger("test_generator")


@contextmanager
def stage(name: str, **fields):
    """Замерить этап: пишет `→ name ...` на входе и `✓ name done in Xs ...` на выходе.

    Возвращает изменяемый dict — положенные в него значения (напр. res["chars"] = 1234)
    попадут в строку завершения. При исключении пишет `✗ name failed after Xs`.
    """
    result: dict = dict(fields)
    extra = " ".join(f"{k}={v}" for k, v in result.items())
    log.info("→ %s%s", name, f" {extra}" if extra else "")
    t0 = time.perf_counter()
    try:
        yield result
    except Exception as e:
        dt = time.perf_counter() - t0
        log.error("✗ %s failed after %.2fs: %s", name, dt, e)
        raise
    else:
        dt = time.perf_counter() - t0
        extra = " ".join(f"{k}={v}" for k, v in result.items())
        log.info("✓ %s done in %.2fs%s", name, dt, f" | {extra}" if extra else "")
