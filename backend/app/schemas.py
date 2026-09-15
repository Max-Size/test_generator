from enum import Enum

from pydantic import BaseModel, Field, model_validator


class QuestionType(str, Enum):
    single = "single"          # один правильный вариант
    multiple = "multiple"      # несколько правильных вариантов
    true_false = "true_false"  # верно/неверно
    short = "short"            # короткий текстовый ответ


class Question(BaseModel):
    id: int
    type: QuestionType
    text: str
    # для single/multiple/true_false — список вариантов; для short — пустой
    options: list[str] = Field(default_factory=list)
    # индексы правильных вариантов (для choice) ЛИБО [0]/[1] для true_false
    correct_indexes: list[int] = Field(default_factory=list)
    # эталонный текст (для short)
    correct_text: str | None = None
    explanation: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Question":
        if self.type in (QuestionType.single, QuestionType.multiple, QuestionType.true_false):
            if len(self.options) < 2:
                raise ValueError("нужно минимум 2 варианта")
            if not self.correct_indexes:
                raise ValueError("не указан правильный вариант")
            if any(i < 0 or i >= len(self.options) for i in self.correct_indexes):
                raise ValueError("correct_indexes вне диапазона options")
            if self.type == QuestionType.single and len(self.correct_indexes) != 1:
                raise ValueError("для single должен быть ровно один правильный вариант")
        if self.type == QuestionType.short and not self.correct_text:
            raise ValueError("для short нужен correct_text")
        return self


class Quiz(BaseModel):
    title: str
    questions: list[Question]


class SourceKind(str, Enum):
    material = "material"            # учебная теория / конспект — по содержанию строим тест
    specification = "specification"  # спецификация экзамена: структура, темы, типы заданий
    sample = "sample"                # образец варианта / примеры заданий


class SourceAnalysis(BaseModel):
    """Результат предварительного разбора загруженных документов.

    Один файл может содержать сразу несколько категорий информации
    (например, спецификация + образец варианта), поэтому kinds — список.
    """
    kinds: list[SourceKind]
    summary: str                       # чем является материал в целом
    exam_structure: str | None = None  # описание структуры экзамена (если есть спецификация)
    topics: list[str] = Field(default_factory=list)       # темы / элементы содержания
    task_types: list[str] = Field(default_factory=list)   # типы заданий по образцу/спецификации
    sample_tasks: list[str] = Field(default_factory=list)  # примеры заданий из образца варианта


class GenerateResponse(BaseModel):
    quiz: Quiz
    source_chars: int
    truncated: bool
    analysis: SourceAnalysis | None = None
