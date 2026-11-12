export type Difficulty = "basic" | "intermediate" | "advanced";
export type ExerciseKind = "multiple_choice" | "true_false" | "short_answer";
export type MaterialStatus = "processing" | "ready" | "failed";
export type Tab = "materials" | "exercises" | "exam" | "progress";

export interface Workspace {
  id: string;
  name: string;
  description: string;
  exam_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceSummary extends Workspace {
  material_count: number;
  exercise_count: number;
  attempt_count: number;
  correct_attempt_count: number;
  accuracy: number;
}

export interface Material {
  id: string;
  workspace_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: MaterialStatus;
  char_count: number;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
}

export interface MaterialDetail extends Material {
  preview: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  next_cursor: string | null;
}

export interface ExerciseOption {
  id: string;
  text: string;
}

export interface Exercise {
  id: string;
  workspace_id: string;
  topic: string;
  difficulty: Difficulty;
  kind: ExerciseKind;
  question: string;
  options: ExerciseOption[];
  hint: string | null;
  created_at: string;
}

export interface GeneratePayload {
  count: number;
  difficulties: Difficulty[];
  focus?: string | null;
  language?: "es" | "en";
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated: boolean;
  model: string | null;
}

export interface GenerateResponse {
  exercises: Exercise[];
  requested: number;
  created: number;
  provider: string;
  warning: string | null;
  cached: boolean;
  duration_ms: number;
  usage: TokenUsage | null;
}

export interface AttemptResult {
  attempt_id: string;
  exercise_id: string;
  is_correct: boolean;
  score: number;
  correct_answer: string;
  feedback: string;
  explanation: string;
  provider: string;
  warning: string | null;
}

export interface AttemptHistoryItem {
  id: string;
  exercise_id: string;
  question: string;
  topic: string;
  difficulty: Difficulty;
  kind: ExerciseKind;
  answer: string;
  is_correct: boolean;
  score: number;
  created_at: string;
}

export interface TopicStat {
  topic: string;
  attempts: number;
  correct: number;
  accuracy: number;
}

export interface DifficultyStat {
  difficulty: Difficulty;
  attempts: number;
  correct: number;
  accuracy: number;
}

export interface RecentAttempt {
  id: string;
  exercise_id: string;
  question: string;
  topic: string;
  difficulty: Difficulty;
  answer: string;
  is_correct: boolean;
  score: number;
  created_at: string;
}

export interface TopicMastery {
  topic: string;
  topic_key: string;
  attempts: number;
  correct: number;
  accuracy: number;
  mastery: number;
  streak: number;
  interval_days: number;
  due_at: string;
  last_attempt_at: string | null;
  is_due: boolean;
}

export interface ErrorPattern {
  topic: string;
  error_type: string;
  count: number;
  detail: string;
  last_seen_at: string;
}

export interface Progress {
  workspace_id: string;
  total_exercises: number;
  attempted_exercises: number;
  total_attempts: number;
  correct_attempts: number;
  accuracy: number;
  by_difficulty: DifficultyStat[];
  by_topic: TopicStat[];
  weak_topics: TopicStat[];
  recent_attempts: RecentAttempt[];
  mastery: TopicMastery[];
  due_topics: TopicMastery[];
  error_patterns: ErrorPattern[];
  average_mastery: number;
}

export interface PlanStep {
  title: string;
  reason: string;
  action: string;
  focus_topic: string | null;
  suggested_difficulty: Difficulty;
  suggested_count: number;
}

export interface StudyPlan {
  workspace_id: string;
  summary: string;
  steps: PlanStep[];
  weak_topics: TopicStat[];
  due_topics: TopicMastery[];
  error_patterns: ErrorPattern[];
  generated_at: string;
}

export interface AuthUser {
  id: string;
  username: string;
  display_name: string;
  is_default: boolean;
  created_at: string;
}

export interface AuthStatus {
  auth_required: boolean;
  authenticated: boolean;
  user: AuthUser | null;
  has_users: boolean;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
}

export interface Health {
  status: string;
  app: string;
  environment: string;
  llm_mode: "auto" | "ollama" | "offline";
  llm_provider: string;
  model: string | null;
  background_queue_depth: number;
}

export interface GenerationMetric {
  id: string;
  workspace_id: string;
  provider: string;
  model: string | null;
  status: string;
  error_code: string | null;
  requested: number;
  created: number;
  cached: boolean;
  duration_ms: number;
  context_chars: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_tokens: boolean;
  created_at: string;
}

export interface GenerationMetrics {
  workspace_id: string;
  total_generations: number;
  cached_generations: number;
  cache_hit_rate: number;
  average_duration_ms: number;
  total_tokens: number;
  average_tokens: number;
  recent: GenerationMetric[];
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}


export interface GuideStep {
  title: string;
  detail: string;
}

export interface Guide {
  exercise_id: string;
  concept: string;
  example: string;
  steps: GuideStep[];
  provider: string;
  created_at: string;
}

export type ExamStatus = "active" | "submitted" | "expired";

export interface ExamQuestion {
  id: string;
  position: number;
  kind: ExerciseKind;
  difficulty: Difficulty;
  topic: string;
  question: string;
  options: ExerciseOption[];
  answer: string;
}

export interface Exam {
  id: string;
  workspace_id: string;
  status: ExamStatus;
  time_limit_seconds: number;
  total_questions: number;
  correct_count: number;
  score: number;
  duration_seconds: number | null;
  started_at: string;
  expires_at: string;
  submitted_at: string | null;
  seconds_remaining: number;
  questions: ExamQuestion[];
}

export interface ExamStartPayload {
  count: number;
  difficulties: Difficulty[];
  time_limit_minutes?: number;
}

export interface ExamResultItem {
  id: string;
  position: number;
  kind: ExerciseKind;
  difficulty: Difficulty;
  topic: string;
  question: string;
  options: ExerciseOption[];
  answer: string;
  is_correct: boolean;
  score: number;
  feedback: string;
  correct_answer: string;
  explanation: string;
}

export interface ExamResult {
  id: string;
  workspace_id: string;
  status: ExamStatus;
  total_questions: number;
  correct_count: number;
  score: number;
  duration_seconds: number | null;
  time_limit_seconds: number;
  started_at: string;
  submitted_at: string | null;
  items: ExamResultItem[];
}
