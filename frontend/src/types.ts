export type QuestionType = "single" | "multiple" | "true_false" | "short";

export interface Question {
  id: number;
  type: QuestionType;
  text: string;
  options: string[];
  correct_indexes: number[];
  correct_text: string | null;
  explanation: string | null;
}

export interface Quiz {
  title: string;
  questions: Question[];
}

export type SourceKind = "material" | "specification" | "sample";

export interface SourceAnalysis {
  kinds: SourceKind[];
  summary: string;
  exam_structure: string | null;
  topics: string[];
  task_types: string[];
  sample_tasks: string[];
}

export type TruncatedFileReason = "partial" | "dropped";

export interface TruncatedFile {
  filename: string;
  reason: TruncatedFileReason;
}

export interface GenerateResponse {
  quiz: Quiz;
  source_chars: number;
  truncated: boolean;
  truncated_files?: TruncatedFile[];
  analysis: SourceAnalysis | null;
}
