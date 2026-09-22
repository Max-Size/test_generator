import json
import os

# polza_model_context_tokens не имеет дефолта (обязательна в .env) — в тестовой среде
# .env не создаётся, поэтому задаём значение здесь, до импорта app.config.settings.
os.environ.setdefault("POLZA_MODEL_CONTEXT_TOKENS", "128000")


def parse_sse(response) -> list[dict]:
    """Разобрать SSE-тело ответа /api/generate в список событий."""
    events = []
    for frame in response.text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        assert frame.startswith("data: ")
        events.append(json.loads(frame[len("data: "):]))
    return events


def sse_result(response) -> dict:
    """Вернуть `data` события `result`; при событии `error` — упасть с его содержимым."""
    events = parse_sse(response)
    for evt in events:
        if evt["type"] == "error":
            raise AssertionError(f"unexpected SSE error event: {evt}")
    result = next(e for e in events if e["type"] == "result")
    return result["data"]
