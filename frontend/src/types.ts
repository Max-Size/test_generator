export type QuestionType = "single" | "multiple" | "true_false" | "short";

export interface Diagram {
  image_base64: string;
  alt_text: string;
}

export interface Question {
  id: number;
  type: QuestionType;
  text: string;
  options: string[];
  correct_indexes: number[];
  correct_text: string | null;
  explanation: string | null;
  diagram: Diagram | null;
}

export interface Quiz {
  title: string;
  questions: Question[];
}

export type SourceKind = "material" | "specification" | "sample";

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
}

export type ProgressStage = "extract" | "generate";

export interface ExtractDetail {
  filename: string;
  processed: number;
  total: number;
}

export type ProgressState =
  | { stage: "extract"; detail: ExtractDetail }
  | { stage: "generate"; detail: string | null };
