export interface Exam {
  id: number
  user_id: number
  video_url: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  total_score: number | null
  created_at: string
  updated_at: string
}

export interface ExamEvent {
  id: number
  exam_id: number
  time_seconds: number
  actor: string | null
  event_type: string
  event_data: Record<string, unknown> | null
  source: 'video' | 'audio' | 'sensor' | 'fusion'
  confidence: number
}

export interface ScoreItem {
  phase: string
  rule_code: string
  rule_name: string
  max_score: number
  actual_score: number
  deduction_reason: string | null
}

export interface ScoreResult {
  exam_id: number
  total_score: number
  max_total: number
  items: ScoreItem[]
  phase_scores: Record<string, { score: number; max_score: number }>
}

export interface ExamStatus {
  id: number
  status: string
  progress: number
  stage?: string
  substep?: string
  detail?: string
}

export interface SensorData {
  id: number
  exam_id: number
  compression_compliance_rate: number
  ventilation_compliance_rate: number
  ccf_percentage: number
  avg_compression_depth: number | null
  avg_compression_rate: number | null
  total_compressions: number | null
  total_ventilations: number | null
}

export interface TranscriptSegment {
  start: number
  end: number
  text: string
  speaker: string | null
  speaker_role: 'doctor' | 'nurse' | 'driver' | 'unknown' | null
  similarity?: number
}

export interface VoiceMatch {
  time: number
  rule_code: string
  rule_name: string
  phase: string
  score: number
  similarity: number
  matched_text: string
  matched_template: string
  speaker: string | null
  speaker_role: string | null
  role_correct: boolean
}

export interface ExamDebugData {
  transcription: TranscriptSegment[]
  voice_matches: VoiceMatch[]
  speaker_roles: Record<string, string>
}
