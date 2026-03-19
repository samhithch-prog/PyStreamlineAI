export type StartInterviewResponse = {
  session_id: string;
  websocket_path: string;
  opening_question: string;
  interview_type: "mixed" | "technical" | "behavioral";
  interview_duration_seconds: number;
  max_turns: number;
};

export type TranscriptMessage = {
  speaker: "ai" | "candidate" | "system";
  text: string;
  timestamp: string;
};

export type EvaluationSignals = {
  technical_accuracy: number;
  communication_clarity: number;
  confidence: number;
  overall_rating: number;
  summary_text: string;
};

export type InterviewResultResponse = {
  session_id: string;
  candidate_name: string;
  role: string;
  interview_type: "mixed" | "technical" | "behavioral";
  status: "in_progress" | "completed";
  turn_count: number;
  max_turns: number;
  current_question: string;
  evaluation_signals: Record<string, number | string>;
  started_at: string;
  ended_at: string | null;
  transcripts: Array<{
    speaker: "ai" | "candidate" | "system";
    text: string;
    sequence_no: number;
    created_at: string;
  }>;
  ai_questions: Array<{
    id: string;
    question_order: number;
    question_text: string;
    created_at: string;
  }>;
  candidate_responses: Array<{
    id: string;
    response_order: number;
    transcript_text: string;
    created_at: string;
  }>;
  evaluation_summary: EvaluationSignals | null;
};

export type WebSocketTokenResponse = {
  ws_token: string;
  token_type: "Bearer";
  expires_in: number;
  session_id: string;
};

export type AccessTokenResponse = {
  access_token: string;
  token_type: "Bearer";
  expires_in: number;
};
