export interface HardwareInfo {
  gpu: string | null;
  vram: string | null;
  nvenc: boolean;
}

export interface ActiveJob {
  slug: string;
  topic: string;
  format: "short" | "long";
  style: string;
  status: "RUNNING" | "DONE" | "ERROR";
  started_at: number;
  finished_at: number | null;
  error: string | null;
}

export interface YouTubeChannelInfo {
  id: string | null;
  title: string;
  custom_url?: string | null;
  subscribers: number;
  video_count: number;
  view_count?: number;
  thumbnail_url?: string | null;
}

export type YouTubeProfileKey = "studio" | "clipper";

export interface YouTubeProfileStatus {
  profile: YouTubeProfileKey;
  label: string;
  connected: boolean;
  has_refresh_token: boolean;
  channel: YouTubeChannelInfo | null;
  token_path: string | null;
  error: string | null;
}

export interface YouTubeUploadReceipt {
  video_id: string;
  url: string;
  watch_url: string;
  studio_url: string;
  title: string;
  description: string;
  hashtags: string[];
  tags: string[];
  category_id: string;
  privacy_status: "private" | "unlisted" | "public";
  publish_at?: string | null;
  is_short: boolean;
  thumbnail_uploaded?: boolean;
  profile?: YouTubeProfileKey;
  channel_title?: string | null;
  channel_id?: string | null;
  uploaded_at: string;
  folder?: string;
  local_clip_deleted?: boolean;
  freed_mb?: number;
}

export interface YouTubeUploadJob {
  job_id: string;
  kind: "project" | "clip" | "file";
  profile?: YouTubeProfileKey;
  id: string;
  channel?: string | null;
  title: string;
  privacy_status: string;
  status: "UPLOADING" | "DONE" | "ERROR";
  progress: number;
  bytes_sent: number;
  total_bytes: number;
  started_at: number;
  finished_at: number | null;
  receipt: YouTubeUploadReceipt | null;
  error: string | null;
}

export interface YouTubeStatus {
  profile?: YouTubeProfileKey;
  has_client_secret: boolean;
  client_secret_path: string | null;
  client_type: "installed" | "web" | null;
  client_id_preview: string | null;
  project_id: string | null;
  redirect_uri: string;
  connected: boolean;
  has_refresh_token: boolean;
  channel: YouTubeChannelInfo | null;
  token_path: string | null;
  error: string | null;
  profiles?: Record<YouTubeProfileKey, YouTubeProfileStatus>;
  categories: Record<string, string>;
  active_uploads?: YouTubeUploadJob[];
  uploads?: YouTubeUploadReceipt[];
}

export interface YouTubeMetadataPreview {
  kind: "project" | "clip" | "file";
  default_profile?: YouTubeProfileKey;
  id: string;
  channel?: string | null;
  folder: string;
  video_path: string;
  video_size_mb: number;
  video_info: { width: number; height: number; duration: number; is_short: boolean };
  is_short: boolean;
  title: string;
  title_options?: string[];
  description: string;
  hashtags: string[];
  tags: string[];
  category_id: string;
  category_name: string;
  privacy_status: "private" | "unlisted" | "public";
  publish_at: string | null;
  made_for_kids: boolean;
  contains_synthetic_media: boolean;
  thumbnail_path: string | null;
  human_approved: boolean;
  existing_upload: YouTubeUploadReceipt | null;
}

export interface StudioStatus {
  studio: string;
  version: string;
  hardware: HardwareInfo;
  skills_count: number;
  skills: string[];
  styles_count: number;
  has_voice_sample: boolean;
  voice_sample_url: string | null;
  voice_sample_bytes: number;
  voicestudio: {
    url: string;
    online: boolean;
    profiles: Array<{ id?: string; name?: string; [k: string]: unknown }>;
  };
  youtube?: {
    connected: boolean;
    has_client_secret: boolean;
    channel: YouTubeChannelInfo | null;
    profiles?: Record<YouTubeProfileKey, YouTubeProfileStatus>;
  };
  subscribers: number;
  operating_cost: string;
  active_jobs: ActiveJob[];
  projects_count: number;
  logs: string[];
  timestamp: number;
}

export interface StyleTokens {
  bg: string;
  surface: string;
  border: string;
  text: string;
  muted: string;
  accent: string;
  accent2: string;
}

export interface StyleItem {
  style_id: string;
  name: string;
  catalog: "claude-video" | "lemo-opuscar";
  has_template: boolean;
  best_for: string;
  mood: string;
  hex_colors: string[];
  tokens: StyleTokens;
}

export interface QueueItem {
  id: string;
  topic: string;
  category: string;
  format: string;
  hook: string;
  research_status: string;
  script_status: string;
  production_status: string;
  priority: string;
  notes: string;
  slug: string;
}

export interface ProjectSummary {
  slug: string;
  topic: string;
  format: "short" | "long";
  resolution?: string;
  created_at?: string;
  style?: { id: string; name?: string; tokens?: StyleTokens };
  hook?: string;
  video?: string | null;
  video_url?: string | null;
  has_metadata: boolean;
  has_checklist: boolean;
  has_review: boolean;
  qa_passed?: boolean;
  qa_verdict?: string;
  metrics?: Record<string, unknown>;
  human_approved: boolean;
  youtube_upload?: YouTubeUploadReceipt | null;
  frames: string[];
  job_status: string;
}

export interface ComplianceItem {
  rule: string;
  status: string;
  detail: string;
}

export interface ReviewReport {
  passed: boolean;
  verdict: string;
  metrics: {
    resolution?: string;
    format_type?: string;
    fps?: number;
    video_codec?: string;
    duration?: number;
    size_mb?: number;
    bitrate_kbps?: number;
    audio_codec?: string;
    audio_channels?: number;
    audio_sample_rate?: number;
    loudness_lufs?: number | null;
    loudness_lra?: number | null;
    true_peak_dbtp?: number | null;
    motion_verified?: boolean;
    unique_frame_count?: number;
    sampled_frames?: string[];
  };
  findings: Array<{ severity: string; category: string; issue: string }>;
  compliance: ComplianceItem[];
}

export interface ProjectDetail extends ProjectSummary {
  review: ReviewReport | null;
  metadata_md: string | null;
  checklist_md: string | null;
  review_md: string | null;
  script_md: string | null;
}

export interface ClipperInProgress {
  clip_id?: string;
  trigger_idx: number;
  stage: "WAITING_POST_PAD" | "EXPORTING_NVENC" | string;
  tier: string;
  archetype: string;
  score: number;
  start_idx?: number;
  end_idx?: number;
  pre_pad_sec?: number;
  post_pad_sec?: number;
}

export interface ClipperHistoryPoint {
  idx: number;
  time: string;
  total: number;
  chat: number;
  audio: number;
  visual: number;
  txt: number;
  tier: string;
  triggered: boolean;
}

export interface ClipperLiveState {
  running: boolean;
  status: string;
  pid?: number;
  url: string;
  platform: "youtube" | "twitch" | "stream";
  channel: string;
  twitch_channel?: string | null;
  youtube_video_id?: string | null;
  started_at: number;
  updated_at: number;
  threshold: number;
  chat_pre_pad: number;
  audio_pre_pad: number;
  post_pad: number;
  layout: string;
  nvenc: boolean;
  keywords: string[];
  segments_scanned: number;
  clips_completed: number;
  in_progress_clips: ClipperInProgress[];
  latest_segment: {
    idx: number;
    time: string;
    total_score: number;
    tier: string;
    archetype: string;
    trigger_source: string;
    synergy: number;
    synergy_reasons: string[];
    chat: {
      connected?: boolean;
      msgs_in_window?: number;
      unique_authors?: number;
      ratio?: number;
      is_explosion?: boolean;
      score: number;
    };
    audio: { rms_db?: number; burst_ratio?: number; vocal_excitement?: number; score: number };
    visual: { mean_delta?: number; scene_cuts?: number; score: number };
    transcript_score: { score: number; archetype?: string; wps?: number };
    transcript: string;
  } | null;
  history: ClipperHistoryPoint[];
  reconnects?: number;
}

export interface HumanClipReview {
  verdict: "POST" | "MAYBE" | "SKIP";
  human_score: number;
  swipe_stop: number;
  clarity: number;
  entertainment: number;
  share_loop: number;
  gut_reaction: string;
  edit_tip: string;
  would_post: boolean;
  model: string;
  reviewed_at: number;
}

export interface LiveClipItem {
  clip_id: string;
  channel: string;
  video_url: string;
  size_mb: number;
  mtime: number;
  captured_at: string;
  total_score: number;
  tier: string;
  archetype: string;
  trigger_source: string;
  synergy: number;
  synergy_reasons: string[];
  pre_pad_used: number;
  post_pad_used: number;
  smart_trim_offset_sec: number;
  transcript: string;
  audio: Record<string, unknown>;
  chat: Record<string, unknown>;
  visual: Record<string, unknown>;
  transcript_score: Record<string, unknown>;
  metadata_md: string;
  checklist_md: string;
  human_approved: boolean;
  human_review?: HumanClipReview | null;
  needs_human_review?: boolean;
  youtube_upload?: YouTubeUploadReceipt | null;
}

export interface LiveClipperSession {
  channel: string;
  running: boolean;
  state: ClipperLiveState;
  logs: string[];
}

export interface DiscoveredStream {
  id: string;
  platform: "twitch" | "youtube";
  login: string;
  display_name: string;
  url: string;
  title: string;
  game: string;
  viewers: number;
  language: string;
  thumbnail_url: string;
  is_watchlist?: boolean;
  clip_ready?: boolean;
  recommended_asr?: "whistle" | "hinglish";
  recommended_lang?: "en" | "hi";
  opportunity_score: number;
  suggested_channel: string;
  already_clipping?: boolean;
}

export interface AutoScoutState {
  enabled: boolean;
  game: string;
  languages: string[];
  max_parallel: number;
  poll_interval_sec: number;
  threshold: number;
  max_clip_sec: number;
  layout: string;
  last_scan_at: number;
  last_started: Array<{ channel: string; url: string; pid: number; display_name?: string; viewers?: number }>;
  last_error: string | null;
}

export interface GroqUsageSummary {
  configured: boolean;
  model: string;
  day: string;
  rpm_used: number;
  rpm_soft_cap: number;
  llm_calls_today: number;
  whisper_calls_today: number;
  whisper_min_today: number;
  rpd_soft_cap: number;
  calls_saved: number;
  batch_size: number;
}

export interface LiveClipperStatus {
  running: boolean;
  running_count?: number;
  sessions?: LiveClipperSession[];
  state: ClipperLiveState | null;
  in_progress_count: number;
  clips_count: number;
  clips: LiveClipItem[];
  logs: string[];
  auto_scout?: AutoScoutState;
  groq_usage?: GroqUsageSummary;
}
