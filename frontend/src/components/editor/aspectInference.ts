import { Video } from "@/types";

export type CanvasAspectRatio = "9:16" | "1:1" | "16:9";

const ASPECT_INFERENCE_TOLERANCE = 0.14;

const STANDARD_RATIOS: Array<{ aspect: CanvasAspectRatio; ratio: number }> = [
  { aspect: "9:16", ratio: 9 / 16 },
  { aspect: "1:1", ratio: 1 },
  { aspect: "16:9", ratio: 16 / 9 },
];

function parseResolution(value: string | null | undefined): { width: number; height: number } | null {
  if (!value) return null;
  const raw = value.trim().toLowerCase().replace(/\s+/g, "");
  const parts = raw.split("x");
  if (parts.length !== 2) return null;
  const width = Number(parts[0]);
  const height = Number(parts[1]);
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return { width, height };
}

function readMetadataNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const raw = record[key];
    const parsed =
      typeof raw === "number"
        ? raw
        : typeof raw === "string"
        ? Number(raw)
        : Number.NaN;
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return null;
}

function extractVideoDimensions(video: Video): { width: number; height: number } | null {
  const parsedResolution = parseResolution(video.resolution);
  if (parsedResolution) return parsedResolution;

  const metadata = (video.external_metadata_json || {}) as Record<string, unknown>;
  const width = readMetadataNumber(metadata, ["width", "video_width", "source_width"]);
  const height = readMetadataNumber(metadata, ["height", "video_height", "source_height"]);
  if (width && height) return { width, height };

  const probe = metadata.editor_preview_probe;
  if (probe && typeof probe === "object" && !Array.isArray(probe)) {
    const probeRecord = probe as Record<string, unknown>;
    const probeWidth = readMetadataNumber(probeRecord, ["width"]);
    const probeHeight = readMetadataNumber(probeRecord, ["height"]);
    if (probeWidth && probeHeight) return { width: probeWidth, height: probeHeight };
  }

  return null;
}

export function inferEditorAspectFromVideo(video: Video): CanvasAspectRatio {
  const dims = extractVideoDimensions(video);
  if (!dims) return "1:1";

  const ratio = dims.width / dims.height;
  const nearest = STANDARD_RATIOS.reduce((best, current) => {
    if (Math.abs(current.ratio - ratio) < Math.abs(best.ratio - ratio)) return current;
    return best;
  }, STANDARD_RATIOS[0]);

  const relativeDelta = Math.abs(nearest.ratio - ratio) / nearest.ratio;
  if (relativeDelta > ASPECT_INFERENCE_TOLERANCE) return "1:1";
  return nearest.aspect;
}

export function aspectDims(aspect: CanvasAspectRatio): { width: number; height: number } {
  if (aspect === "1:1") return { width: 720, height: 720 };
  if (aspect === "16:9") return { width: 1280, height: 720 };
  return { width: 720, height: 1280 };
}

export function safeAreaPresetForAspect(aspect: CanvasAspectRatio): "tiktok" | "square" | "landscape" {
  if (aspect === "1:1") return "square";
  if (aspect === "16:9") return "landscape";
  return "tiktok";
}
