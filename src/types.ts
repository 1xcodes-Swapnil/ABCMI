export type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface EndpointDef {
  method: Method;
  path: string;
  category: string;
  description: string;
  rbac: string;
  phase: string;
  sampleBody?: string;
}

export type MeetingStatus = 'created' | 'scheduled' | 'live' | 'paused' | 'processing' | 'completed' | 'failed';

export interface MeetingItem {
  id: string;
  title: string;
  description: string;
  status: MeetingStatus;
  primary_language: string;
  scheduled_start?: string;
  duration_minutes?: number;
  audio_uploaded: boolean;
  audio_file_name?: string;
  audio_file_size_mb?: number;
  participants: string[];
  created_at: string;
  updated_at: string;
}

export interface DecisionItem {
  id: string;
  decision_text: string;
  decision_maker: string;
  consensus_level: 'unanimous' | 'majority' | 'contested' | 'directive';
  confidence: number;
  timestamp_offset: number;
  verification_status: 'verified' | 'unverified' | 'rejected';
}

export interface ActionItemDef {
  id: string;
  description: string;
  assignee: string;
  due_date: string;
  priority: 'low' | 'medium' | 'high' | 'critical';
  status: 'pending' | 'in_progress' | 'completed' | 'blocked';
  confidence: number;
  meeting_id: string;
  meeting_title?: string;
}

export interface TopicItem {
  id: string;
  name: string;
  duration_seconds: number;
  sentiment: 'positive' | 'neutral' | 'negative' | 'mixed';
  relevance: number;
}

export interface RiskItem {
  id: string;
  risk_text: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  mitigation_suggestion: string;
  confidence: number;
}

export interface WordToken {
  word: string;
  confidence: number;
  start_ms: number;
  end_ms: number;
}

export interface SpeakerSegment {
  id: string;
  speaker: string;
  speaker_id?: string;
  start_time: string;
  end_time: string;
  start_seconds: number;
  end_seconds: number;
  text: string;
  confidence: number;
  acoustic_confidence?: number;
  language_code: string;
  language_label: string;
  has_overlap?: boolean;
  needs_review?: boolean;
  verified?: boolean;
  words?: WordToken[];
}

export interface MeetingIntelligence {
  meeting_id: string;
  executive_summary: string;
  key_takeaways: string[];
  confidence_score: number;
  decisions: DecisionItem[];
  action_items: ActionItemDef[];
  topics: TopicItem[];
  risks: RiskItem[];
  speaker_segments?: SpeakerSegment[];
}

export interface KnowledgeObject {
  id: string;
  topic: string;
  content: string;
  type: 'decision' | 'action_item' | 'insight' | 'policy' | 'technical_spec';
  version: number;
  superseded_by?: string | null;
  supersedes?: string | null;
  entities: string[];
  confidence: number;
  meeting_id: string;
  created_at: string;
}

export interface GroundedCitation {
  meeting_id: string;
  meeting_title: string;
  timestamp: string;
  speaker: string;
  snippet: string;
}

export interface GroundedQuery {
  id: string;
  query_text: string;
  answer_text: string;
  confidence: number;
  status: 'grounded' | 'insufficient_context' | 'ambiguous';
  citations: GroundedCitation[];
  created_at: string;
  meeting_id?: string;
}

export interface TranslationItem {
  id: string;
  meeting_id: string;
  language_code: string;
  language_name: string;
  translated_summary: string;
  translated_decisions: string[];
  translated_action_items: string[];
  created_at: string;
}

export interface ReportItem {
  id: string;
  meeting_id: string;
  meeting_title: string;
  format: 'markdown' | 'pdf' | 'json' | 'txt';
  created_at: string;
  content: string;
  download_url?: string;
}

export interface NotificationItem {
  id: string;
  event_type: 'meeting.processed' | 'action_item.assigned' | 'decision.recorded' | 'security.alert' | 'stream.completed';
  title: string;
  message: string;
  read: boolean;
  created_at: string;
}

export interface AuditLogItem {
  id: string;
  timestamp: string;
  user_id: string;
  user_email: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  status: 'SUCCESS' | 'DENIED' | 'FAILED';
  sanitized_payload: string;
}

export interface HardwareTelemetry {
  cpu?: string;
  cores?: number;
  ram_gb?: number;
  os?: string;
  python_version?: string;
  device?: string;
}

export interface BenchmarkSampleResult {
  id?: number;
  run_id: string;
  sample_id: string;
  dataset_name: string;
  dataset_version: string;
  audio_path: string;
  language: string;
  duration_seconds: number;
  model_name: string;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED';
  wer?: number | null;
  cer?: number | null;
  der?: number | null;
  missed_speech_rate?: number | null;
  false_alarm_rate?: number | null;
  speaker_confusion_rate?: number | null;
  mean_boundary_error_ms?: number | null;
  processing_time_seconds?: number | null;
  real_time_factor?: number | null;
  error_message?: string | null;
  created_at: string;
  reference_transcript?: string;
  predicted_transcript?: string;
}

export interface BenchmarkRun {
  run_id: string;
  dataset_name: string;
  dataset_version: string;
  model_name: string;
  provider: string;
  device: string;
  language: string;
  samples_requested: number;
  samples_completed: number;
  samples_failed: number;
  status: 'SUCCESS' | 'FAILED' | 'RUNNING' | 'PARTIAL';
  mean_wer?: number | null;
  mean_cer?: number | null;
  mean_der?: number | null;
  mean_rtf?: number | null;
  hardware_info?: HardwareTelemetry;
  created_at: string;
  completed_at?: string;
  error_summary?: string | null;
  samples?: BenchmarkSampleResult[];
}

export interface BenchmarkDatasetInfo {
  key: string;
  name: string;
  version: string;
  publisher: string;
  homepage: string;
  download_url?: string;
  description: string;
  expected_audio_format: string;
  supported_tasks: string[];
  requires_auth: boolean;
  auth_instructions?: string;
  recommended_sample_size: number;
  target_metrics: string;
  license_notice: string;
  ground_truth_format: string;
  env_var: string;
}

export interface AuthContext {
  token: string;
  user_id: string;
  user_name: string;
  user_email: string;
  role: 'host' | 'admin' | 'member' | 'security_officer';
  tenant_id: string;
}

export type DomainCategory = 'business' | 'education' | 'healthcare' | 'legal' | 'customer_support' | 'research';

export interface DomainUsecaseDef {
  id: string;
  domain: DomainCategory;
  name: string;
  shortTitle: string;
  description: string;
  iconName: string;
  badge: string;
  complianceStandards: string[];
  keyDeliverables: string[];
  keySections: string[];
  sampleTitle: string;
  primaryMetric: string;
}

export type ReportOutputFormat = 'markdown' | 'pdf' | 'json' | 'txt' | 'html';
