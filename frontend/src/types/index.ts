export type UserTier = "starter" | "creator" | "agency";
export type OnboardingRole = "creator" | "founder" | "agency" | "team";

export interface User {
  id: string;
  email: string;
  tier: UserTier;
  videos_used: number;
  onboarding_completed_at?: string | null;
  onboarding_skipped_at?: string | null;
  onboarding_role?: OnboardingRole | null;
  onboarding_metadata_json?: Record<string, unknown> | null;
  billing_plan?: string;
  subscription_status?: string;
  trial_ends_at?: string | null;
  billing_period_start?: string | null;
  billing_period_end?: string | null;
  platforms_allowed?: number;
  created_at: string;
  updated_at: string;
}

export interface OnboardingStatus {
  completed_at: string | null;
  skipped_at: string | null;
  role: OnboardingRole | null;
  tier: UserTier;
  metadata: Record<string, unknown>;
  should_onboard: boolean;
}

export interface OnboardingProfilePatch {
  role?: OnboardingRole | null;
  tier?: UserTier | null;
  metadata?: Record<string, unknown> | null;
}

export type VideoSourceType = "upload" | "youtube" | "youtube_single" | "youtube_playlist" | "instagram" | "facebook" | "tiktok" | "x" | "twitch";
export type ClipProfile = "viral" | "sermon";
export type VideoStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "scoring"
  | "ready"
  | "error";

export type VideoImportState =
  | "not_applicable"
  | "queued"
  | "metadata_extracting"
  | "downloadable"
  | "downloading"
  | "blocked"
  | "replacement_upload_required"
  | "helper_required"
  | "embed_only"
  | "processing"
  | "ready"
  | "failed_retryable"
  | "failed_terminal";

export interface VideoGenerateClipsResponse {
  video_id: string;
  status: "queued" | "already_scoring";
  clip_profile: ClipProfile;
  message: string;
}

export interface Video {
  id: string;
  user_id: string;
  title: string | null;
  source_type: VideoSourceType;
  source_url: string | null;
  clip_profile?: ClipProfile;
  source_video_id?: string | null;
  source_playlist_id?: string | null;
  source_playlist_title?: string | null;
  playlist_index?: number | null;
  import_parent_id?: string | null;
  embed_url?: string | null;
  import_state?: VideoImportState;
  import_state_ui?: string | null;
  import_mode?: "server_download" | "embed_only" | "manual_upload";
  is_download_blocked?: boolean;
  error_code?: string | null;
  debug_error_message?: string | null;
  external_metadata_json?: Record<string, unknown>;
  storage_key: string | null;
  source_download_url?: string | null;
  editor_preview_download_url?: string | null;
  editor_preview_status?: "pending" | "ready" | "failed" | null;
  duration_sec: number | null;
  resolution: string | null;
  file_size_bytes: number | null;
  raw_source_expires_at?: string | null;
  raw_source_days_remaining?: number | null;
  status: VideoStatus;
  error_message: string | null;
  clip_count: number;
  created_at: string;
  updated_at: string;
  thumbnail_url?: string | null;
}

export interface VideoListItem {
  id: string;
  title: string | null;
  status: VideoStatus;
  duration_sec: number | null;
  clip_count: number;
  created_at: string;
  thumbnail_url: string | null;
  source_type: VideoSourceType;
  source_url: string | null;
  clip_profile?: ClipProfile;
  source_video_id: string | null;
  source_playlist_id: string | null;
  source_playlist_title: string | null;
  playlist_index: number | null;
  import_parent_id: string | null;
  embed_url: string | null;
  import_state: VideoImportState;
  import_state_ui: string | null;
  import_mode: "server_download" | "embed_only" | "manual_upload";
  is_download_blocked: boolean;
  error_code: string | null;
  error_message: string | null;
  raw_source_expires_at?: string | null;
  raw_source_days_remaining?: number | null;
}

export interface YouTubeImportResponse {
  video_id?: string | null;
  playlist_import_id?: string | null;
  import_kind: "single" | "playlist";
  status: string;
  message: string;
  recovery_required?: boolean;
  recovery_reason?: string | null;
  recovery_action?: string | null;
}

export interface PlaylistImportItem {
  id: string;
  title: string | null;
  status: VideoStatus;
  import_state: VideoImportState;
  import_state_ui: string | null;
  playlist_index: number | null;
  source_video_id: string | null;
  embed_url: string | null;
  thumbnail_url: string | null;
  import_mode: "server_download" | "embed_only" | "manual_upload";
  is_download_blocked: boolean;
  error_code: string | null;
  error_message: string | null;
}

export interface PlaylistImport {
  id: string;
  source_url: string;
  playlist_id: string;
  title: string | null;
  status: string;
  total_items: number;
  completed_items: number;
  failed_items: number;
  created_at: string;
  updated_at: string;
  items: PlaylistImportItem[];
}

export interface TranscriptSegmentPayload {
  id: number;
  start: number;
  end: number;
  text: string;
  words: Array<{
    word: string;
    start: number;
    end: number;
    confidence?: number;
    segment_index?: number;
  }>;
}

export interface VideoTranscript {
  video_id: string;
  word_count: number;
  duration: number;
  language: string | null;
  full_text: string;
  segments: TranscriptSegmentPayload[];
}

export type ClipStatus = "pending" | "ready" | "exported";

export interface Clip {
  id: string;
  video_id: string;
  start_time: number;
  end_time: number;
  duration_sec: number | null;
  score: number | null;
  hook_score: number | null;
  energy_score: number | null;
  title: string | null;
  hashtags: string[] | null;
  title_options: string[] | null;
  hashtag_options: string[][] | null;
  copy_generation_status: string | null;
  copy_generation_error: string | null;
  thumbnail_key: string | null;
  thumbnail_url: string | null;
  transcript_text: string | null;
  status: ClipStatus;
  created_at: string;
  updated_at: string;
}

export type AspectRatio = "original" | "9:16" | "16:9" | "1:1";
export type CaptionStyle =
  | "bold_boxed"
  | "sermon_quote"
  | "clean_minimal"
  | "kinetic_bold"
  | "cinema_outline"
  | "clean_highlight";
export type CaptionColorVariant = "classic" | "warm" | "cool";
export type CaptionFormat = "none" | "burned_in" | "srt";
export type CaptionCadence = "phrase" | "split_line" | "word_by_word" | "subtitle_block";
export type ExportStatus = "queued" | "rendering" | "ready" | "error";

export interface ClipOverlayAsset {
  id: string;
  clip_id: string;
  user_id: string;
  original_filename: string | null;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  download_url: string;
  created_at: string;
}

export interface ExportOverlayImageConfig {
  x: number;
  y: number;
  width: number;
  opacity: number;
}

export interface ExportOverlayTextHighlight {
  word_index: number;
  color: string;
}

export interface ExportOverlayTextConfig {
  text: string;
  x: number;
  y: number;
  font_size: number;
  text_color: string;
  highlights: ExportOverlayTextHighlight[];
}

export interface Export {
  id: string;
  clip_id: string;
  retry_of_export_id: string | null;
  user_id: string;
  aspect_ratio: AspectRatio;
  caption_style: CaptionStyle | null;
  caption_color_variant: CaptionColorVariant;
  caption_format: CaptionFormat;
  caption_cadence: CaptionCadence;
  caption_vertical_position?: number | null;
  caption_scale?: number | null;
  frame_anchor_x?: number | null;
  frame_anchor_y?: number | null;
  frame_zoom?: number | null;
  overlay_image_asset_id?: string | null;
  overlay_image_config?: ExportOverlayImageConfig | null;
  overlay_text_config?: ExportOverlayTextConfig | null;
  storage_key: string | null;
  srt_key: string | null;
  download_url: string | null;
  srt_download_url?: string | null;
  url_expires_at: string | null;
  status: ExportStatus;
  error_message: string | null;
  render_time_sec: number | null;
  reused?: boolean;
  video_id?: string | null;
  video_title?: string | null;
  clip_title?: string | null;
  clip_transcript_text?: string | null;
  clip_thumbnail_url?: string | null;
  clip_title_options?: string[] | null;
  clip_hashtag_options?: string[][] | null;
  clip_copy_generation_status?: string | null;
  clip_copy_generation_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CarouselTemplate {
  id: string;
  name: string;
  description: string;
  renderer: string;
  preview_url: string;
  default_slides: number;
}

export type CarouselSlideType = "hook" | "body" | "cta";

export interface CarouselSlide {
  type: CarouselSlideType | string;
  title?: string;
  text?: string;
  subtitle?: string;
  body?: string;
  bullets?: string[];
  cta_action?: string;
  button_text?: string;
  glow?: string;
  image?: string;
  annotation?: string;
  label?: string;
  subheading?: string;
  [key: string]: unknown;
}

export interface CarouselConfig {
  title: string;
  profile: {
    display_name: string;
    handle: string;
  };
  renderer?: string | null;
  slides: CarouselSlide[];
  [key: string]: unknown;
}

export interface CarouselGenerateResponse {
  config: CarouselConfig;
  provider_used: string;
}

export interface CarouselRenderedSlide {
  index: number;
  key: string;
  url: string;
}

export interface CarouselRenderResponse {
  workspace_id: string;
  slides: CarouselRenderedSlide[];
  zip: {
    key: string;
    url: string;
  };
}

export interface CarouselExport {
  id: string;
  user_id: string;
  template_id: string;
  title: string | null;
  config_json: CarouselConfig;
  slide_keys_json: string[];
  zip_key: string;
  preview_key: string;
  slide_count: number;
  zip_url?: string | null;
  preview_url?: string | null;
  created_at: string;
  updated_at: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: string;
  video_id: string;
  type: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  celery_task_id: string | null;
  attempts: number;
  max_attempts: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TranscriptSegment {
  id: string;
  video_id: string;
  word: string | null;
  start_time: number;
  end_time: number;
  confidence: number | null;
  segment_index: number | null;
  created_at: string;
}

export type SocialPlatform = "instagram" | "threads" | "tiktok" | "facebook" | "youtube" | "x" | "linkedin";

export interface SocialProviderCapabilities {
  supports_connect: boolean;
  supports_publish_now: boolean;
  supports_schedule: boolean;
  supports_video_upload: boolean;
  supports_caption: boolean;
  supports_title: boolean;
  supports_description: boolean;
  supports_hashtags: boolean;
  supports_privacy: boolean;
  supports_multiple_accounts: boolean;
  may_require_user_completion: boolean;
}

export interface SocialProvider {
  platform: SocialPlatform;
  display_name: string;
  setup_status: string;
  setup_message: string | null;
  setup_details?: Record<string, unknown> | null;
  connected_account_count: number;
  capabilities: SocialProviderCapabilities;
}

export interface ConnectedAccount {
  id: string;
  user_id: string;
  platform: SocialPlatform;
  external_account_id: string;
  display_name: string | null;
  username_or_channel_name: string | null;
  destination_type: string;
  token_expires_at: string | null;
  token_expired: boolean;
  last_token_refresh: string | null;
  scopes: string[] | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PublicExportShare {
  export_id: string;
  clip_id: string;
  video_id: string;
  title: string;
  description: string;
  thumbnail_url: string | null;
  media_url: string;
  share_url: string;
}

export type PublishJobStatus =
  | "scheduled"
  | "queued"
  | "publishing"
  | "published"
  | "failed"
  | "waiting_user_action"
  | "provider_not_configured"
  | "cancelled";

export type PublishMode = "now" | "scheduled";

export interface SocialPublishJob {
  id: string;
  user_id: string;
  export_id: string | null;
  clip_id: string | null;
  platform: SocialPlatform;
  connected_account_id: string | null;
  workflow_source_post_id: string | null;
  workflow_run_id: string | null;
  status: PublishJobStatus;
  publish_mode: PublishMode;
  caption: string | null;
  title: string | null;
  description: string | null;
  hashtags: string[] | null;
  privacy: string | null;
  scheduled_for: string | null;
  timezone: string | null;
  destination_display_name: string | null;
  content_title_snapshot: string | null;
  external_post_id: string | null;
  external_post_url: string | null;
  error_message: string | null;
  provider_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PublishCalendarItem extends SocialPublishJob {
  thumbnail_url: string | null;
}

export interface PublishCalendarResponse {
  items: PublishCalendarItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface PlatformCopyFields {
  title: string | null;
  caption: string | null;
  description: string | null;
  hashtags: string[];
}

export type WorkflowCopyMode = "ai_platform" | "reuse_source";
export type WorkflowRunStatus =
  | "waiting_asset"
  | "processing"
  | "queued"
  | "completed"
  | "partial_failed"
  | "failed"
  | "skipped";

export interface LegacySocialWorkflow {
  id: string;
  user_id: string;
  name: string;
  source_account_id: string | null;
  source_platform: SocialPlatform;
  copy_mode: WorkflowCopyMode;
  destination_configs: Array<{
    connected_account_id: string;
    platform: SocialPlatform;
    display_name?: string | null;
    privacy?: string | null;
  }>;
  enabled: boolean;
  cursor_json: Record<string, unknown>;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  user_id: string;
  source_publish_job_id: string | null;
  source_export_id: string | null;
  source_platform: SocialPlatform;
  source_external_post_id: string;
  source_external_url: string | null;
  source_title: string | null;
  source_description: string | null;
  source_published_at: string | null;
  status: WorkflowRunStatus;
  generated_copy_json: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRunList {
  items: WorkflowRun[];
  total: number;
}

export interface WorkflowSourceCapability {
  connected_account_id: string;
  platform: SocialPlatform;
  status: "ready" | "reconnect_required" | "unsupported";
  message: string | null;
  missing_scopes: string[];
}

export interface PlatformCopyGenerateResponse {
  provider_used: "deepseek";
  results: Partial<Record<SocialPlatform, PlatformCopyFields>>;
  errors: Partial<Record<SocialPlatform, string>>;
}

export interface ClipCopyOptionsResponse {
  provider_used: "deepseek";
  titles: string[];
  captions: string[];
  hashtag_sets: string[][];
  platform: SocialPlatform | null;
}

export interface FullVideoExportResponse {
  clip_id: string;
  export_id: string;
  export_status: string;
  reused_existing_export: boolean;
}

export type SocialWorkflowStatus = "active" | "paused";
export type SocialWorkflowCopyMode = "reuse_source" | "platform_ai" | "both";
export type SocialWorkflowImportMode = "manual_select" | "start_now" | "last_n";
export type SocialWorkflowRunStatus =
  | "detected"
  | "importing"
  | "imported_processing"
  | "ready_to_publish"
  | "publishing"
  | "completed"
  | "original_required"
  | "import_failed"
  | "partial_failed";
export type SocialWorkflowSourceStatus = SocialWorkflowRunStatus;

export interface SocialWorkflowRun {
  id: string;
  user_id: string;
  workflow_id: string;
  status: SocialWorkflowRunStatus;
  publish_job_ids_json: string[];
  destination_results_json: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface SocialWorkflowSourcePost {
  id: string;
  user_id: string;
  workflow_id: string;
  source_account_id: string | null;
  source_platform: SocialPlatform;
  external_post_id: string;
  permalink: string | null;
  caption_snapshot: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  status: SocialWorkflowSourceStatus;
  video_id: string | null;
  export_id: string | null;
  workflow_run_id: string | null;
  error_message: string | null;
  raw_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  workflow_run?: SocialWorkflowRun | null;
  publish_jobs?: SocialPublishJob[];
}

export interface SocialWorkflow {
  id: string;
  user_id: string;
  name: string;
  source_platform: SocialPlatform;
  source_account_id: string | null;
  status: SocialWorkflowStatus;
  copy_mode: SocialWorkflowCopyMode;
  auto_publish: boolean;
  destination_targets_json: Array<Record<string, unknown>>;
  poll_cursor_json: Record<string, unknown>;
  last_polled_at: string | null;
  last_error: string | null;
  source_account_status?: "connected" | "needs_reconnection" | "poll_error";
  source_account_action?: string | null;
  source_account_message?: string | null;
  created_at: string;
  updated_at: string;
  source_posts: SocialWorkflowSourcePost[];
}


export interface BrandProfile {
  id: string;
  user_id: string;
  display_name: string;
  handle: string;
  niche: string;
  target_audience: string;
  tone: string;
  use_phrases: string[];
  avoid_phrases: string[];
  ai_cmo_enabled: boolean;
  post_frequency: number;
  preferred_platforms: string[];
  created_at: string;
  updated_at: string;
}

export interface DeveloperApiKey {
  id: string;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface DeveloperUsage {
  plan: string;
  limits: {
    per_hour: number;
    per_day: number;
  };
  usage: {
    this_hour: number;
    today: number;
    hour_percent: number;
    day_percent: number;
    warning: boolean;
  };
  reset: {
    hour_resets_at: string;
    day_resets_at: string;
  };
}

export interface BillingStatus {
  plan_tier: string;
  subscription_status: string;
  trial_ends_at: string | null;
  billing_period_start: string | null;
  billing_period_end: string | null;
  platforms_allowed: number;
  platforms_connected: number;
  storage_quota_bytes: number;
  storage_hard_stop_bytes: number;
  storage_used_bytes: number;
  storage_raw_video_bytes: number;
  storage_editor_asset_bytes: number;
  storage_render_output_bytes: number;
  storage_warning: boolean;
  storage_blocked: boolean;
  stripe_publishable_key: string;
  billing_enabled: boolean;
}

export type ContentQueueStatus = "draft" | "rendering" | "ready" | "approved" | "rejected" | "posted";

export interface ContentQueueItem {
  id: string;
  user_id: string;
  content_type: string;
  config: CarouselConfig;
  slide_urls: string[];
  slide_keys_json: string[];
  zip_key: string | null;
  preview_key: string | null;
  asset_cleanup_at: string | null;
  assets_deleted_at: string | null;
  status: ContentQueueStatus;
  platforms: string[];
  scheduled_at: string | null;
  generation_topic: string | null;
  created_at: string;
  updated_at: string;
}

export * from "./editor";

export interface PostAnalyticsSummary {
  total_posts: number;
  total_views: number;
  total_likes: number;
  total_comments: number;
  total_shares: number;
  total_reach: number;
  total_impressions: number;
  posts_with_errors: number;
  top_platform: string | null;
}

export interface PostAnalyticsTimeseriesPoint {
  date: string;
  platform: SocialPlatform;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  reach: number;
  impressions: number;
}

export interface PostAnalyticsTopPerformer {
  publish_job_id: string;
  platform: SocialPlatform;
  title: string;
  external_post_url: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  reach: number;
  impressions: number;
  fetch_error: string | null;
}

export interface PostAnalyticsSnapshot {
  publish_job_id: string;
  platform: SocialPlatform;
  title: string;
  caption: string | null;
  external_post_id: string | null;
  external_post_url: string | null;
  fetched_at: string | null;
  published_at: string | null;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  reach: number;
  impressions: number;
  fetch_error: string | null;
  raw_response: Record<string, unknown> | null;
}
