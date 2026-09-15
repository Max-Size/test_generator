import os

# polza_model_context_tokens не имеет дефолта (обязательна в .env) — в тестовой среде
# .env не создаётся, поэтому задаём значение здесь, до импорта app.config.settings.
os.environ.setdefault("POLZA_MODEL_CONTEXT_TOKENS", "128000")
