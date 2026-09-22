from pydantic_settings import BaseSettings, SettingsConfigDict

# Бюджет контекста считается от контекстного окна модели (polza_model_context_tokens),
# а не хранится статичной настройкой — см. docs/features/context-budget/spec.md.
# Резерв под системный промпт/врезку анализа/схему ответа + пропорционально max_questions
# под ответ модели (грубая, но консервативная оценка на вопрос).
_BASE_RESERVED_TOKENS = 2_000
_RESERVED_TOKENS_PER_QUESTION = 120
# Консервативный коэффициент символов на токен: кириллица токенизируется плотнее
# латиницы, поэтому берём меньшее значение, чем обычно приводят для английского текста.
_CHARS_PER_TOKEN = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Polza.ai — OpenAI-совместимый API (https://polza.ai/docs/glavnoe/quickstart)
    polza_base_url: str = "https://polza.ai/api/v1"
    polza_api_key: str = ""
    polza_model: str = "openai/gpt-4o"
    # Контекстное окно модели из polza_model, в токенах. Обязательна в .env — обновляется
    # вручную вместе с polza_model. Из неё считается max_context_chars.
    polza_model_context_tokens: int
    # Просить у модели строгий JSON по схеме (response_format=json_schema).
    # Если выбранная модель это не поддерживает — выключить, останется json_object + ретрай.
    polza_json_schema: bool = True
    # strict:true в json_schema — жёсткая гарантия структуры (поддерживают не все модели)
    polza_json_schema_strict: bool = True
    # Температура генерации
    polza_temperature: float = 0.4
    # Таймаут HTTP-запроса к API, секунды
    polza_timeout: float = 180.0

    cors_origins: str = "http://localhost:5173"

    max_files: int = 5
    max_questions: int = 30
    # Максимальный размер одного загружаемого файла.
    max_file_size_mb: int = 20

    # --- Извлечение содержимого документов ---
    # Кэш результатов извлечения (Markdown) по SHA-256 файла
    ingest_cache_dir: str = ".cache/ingest"
    # Домысливать «тяжёлые» страницы PDF (картинки, графики, формулы) через vision-модель
    vision_enabled: bool = True
    # Модель для распознавания страниц-картинок (id в Polza.ai, должна быть мультимодальной)
    vision_model: str = "openai/gpt-4o"
    # DPI рендера страницы PDF в PNG перед отправкой в vision-модель
    vision_dpi: int = 150
    # Максимум страниц одного файла, которые отправляем в vision-модель (ограничение затрат)
    vision_max_pages: int = 20
    # Сколько страниц распознаём параллельно (одновременных запросов к vision-модели)
    vision_concurrency: int = 4
    # Порог: страницы, где текстом извлечено меньше символов, считаем «тяжёлыми»
    vision_min_text_chars: int = 200

    # --- Рисунки к вопросам: TikZ → SVG через tectonic ---
    # путь к бинарнику tectonic
    tikz_bin: str = "tectonic"
    # таймаут компиляции одного рисунка, секунды
    tikz_timeout_s: float = 20
    # сколько рисунков компилируем параллельно
    tikz_concurrency: int = 4
    # сколько раз просим LLM исправить рисунок; компиляций максимум tikz_fix_attempts + 1
    tikz_fix_attempts: int = 2
    # максимальная длина исходника рисунка, символов
    tikz_max_chars: int = 8000

    # уровень логирования бэкенда (DEBUG/INFO/WARNING/ERROR)
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_context_chars(self) -> int:
        reserved = _BASE_RESERVED_TOKENS + self.max_questions * _RESERVED_TOKENS_PER_QUESTION
        return max(0, (self.polza_model_context_tokens - reserved) * _CHARS_PER_TOKEN)


settings = Settings()
