export type EditorProjectStatus = "draft" | "rendering" | "ready" | "error" | "archived";
export type EditorRenderStatus = "queued" | "processing" | "completed" | "failed";
export type EditorRenderPreset = "tiktok" | "reels" | "shorts" | "linkedin" | "square" | "landscape";
export type EditorAssetType = "image" | "logo";

export interface EditorCaptionStyle {
  font_family: string;
  font_size: number;
  text_color: string;
  bg_color: string;
  position: "top" | "middle" | "bottom";
  uppercase: boolean;
}

export interface EditorCaptionGroupTransform {
  anchor_x?: number | null;
  anchor_y?: number | null;
  scale?: number | null;
}

export interface EditorCaptionOverride {
  segment_id?: string | null;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface EditorCaptionConfig {
  enabled: boolean;
  source: "transcript_segments";
  active_word_highlight: boolean;
  style: EditorCaptionStyle;
  group?: EditorCaptionGroupTransform;
  overrides: EditorCaptionOverride[];
}

export interface EditorProjectMeta {
  aspect_auto_inferred_v1?: boolean;
  editor_preview_status?: "pending" | "ready" | "failed" | null;
  editor_preview_key?: string | null;
  editor_preview_source_key?: string | null;
  editor_preview_profile_version?: number | null;
  editor_preview_offset_sec?: number | null;
  editor_preview_duration_sec?: number | null;
  editor_preview_error?: string | null;
  editor_preview_enqueued_at?: string | null;
  editor_preview_updated_at?: string | null;
}

export interface EditorOverlayStyle {
  font_family?: string | null;
  font_size?: number | null;
  font_weight?: number | null;
  alignment?: "left" | "center" | "right" | null;
  color?: string | null;
  bg_color?: string | null;
}

export interface EditorOverlay {
  id: string;
  type: "text" | "image";
  start_sec: number;
  end_sec: number;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation_deg: number;
  opacity: number;
  z_index: number;
  content?: string | null;
  asset_id?: string | null;
  style?: EditorOverlayStyle | null;
}

export interface EditorProjectSchemaV1 {
  version: 1;
  clip_ref: {
    video_id: string;
    clip_id: string;
    source_storage_key?: string | null;
    source_duration_sec?: number | null;
  };
  meta?: EditorProjectMeta;
  canvas: {
    aspect_ratio: "9:16" | "1:1" | "16:9";
    width: number;
    height: number;
    safe_area_preset: EditorRenderPreset;
  };
  trim: {
    start_sec: number;
    end_sec: number;
  };
  reframe: {
    anchor_x: number;
    anchor_y: number;
    zoom: number;
    fit_mode?: "fill" | "fit";
  };
  captions: EditorCaptionConfig;
  overlays: EditorOverlay[];
  export: {
    preset: EditorRenderPreset;
    video_codec: "h264";
    audio_codec: "aac";
  };
}

export interface UserStorageUsage {
  quota_bytes: number;
  hard_stop_bytes: number;
  used_bytes: number;
  raw_video_bytes: number;
  editor_asset_bytes: number;
  render_output_bytes: number;
  warning: boolean;
  blocked: boolean;
}

export interface EditorAsset {
  id: string;
  project_id: string;
  user_id: string;
  asset_type: EditorAssetType;
  storage_key: string;
  original_filename: string | null;
  mime_type: string | null;
  size_bytes: number;
  width: number | null;
  height: number | null;
  download_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface EditorRender {
  id: string;
  project_id: string;
  user_id: string;
  export_id: string | null;
  status: EditorRenderStatus;
  preset: EditorRenderPreset;
  output_storage_key: string | null;
  output_size_bytes: number | null;
  error_message: string | null;
  download_url: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EditorProject {
  id: string;
  user_id: string;
  video_id: string;
  clip_id: string;
  name: string | null;
  status: EditorProjectStatus;
  aspect_ratio: "9:16" | "1:1" | "16:9" | "original";
  trim_start_sec: number;
  trim_end_sec: number;
  is_pinned: boolean;
  revision: number;
  project_json: EditorProjectSchemaV1;
  last_render_id: string | null;
  assets: EditorAsset[];
  latest_render: EditorRender | null;
  storage_usage: UserStorageUsage | null;
  preview_status?: "pending" | "ready" | "failed" | null;
  preview_download_url?: string | null;
  preview_offset_sec?: number | null;
  preview_duration_sec?: number | null;
  preview_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EditorProjectFromClipResponse {
  project_id: string;
}

export interface EditorProjectDuplicateResponse {
  project_id: string;
}
