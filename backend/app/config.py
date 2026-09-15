from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Polza.ai — OpenAI-совместимый API (https://polza.ai/docs/glavnoe/quickstart)
    polza_base_url: str = "https://polza.ai/api/v1"
    polza_api_key: str = ""
    polza_model: str = "openai/gpt-4o"
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
    max_context_chars: int = 24_000
    max_questions: int = 30

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

    # уровень логирования бэкенда (DEBUG/INFO/WARNING/ERROR)
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
