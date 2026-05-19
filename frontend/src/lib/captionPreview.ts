import { AspectRatio, CaptionColorVariant, CaptionStyle } from "@/types";

export interface CaptionPreviewLayout {
  fontSizePx: number;
  lineHeight: number;
  marginXPercent: number;
  marginBottomPercent: number;
  maxCharsPerLine: number;
  maxLines: number;
}

export interface CaptionStyleTheme {
  bold: boolean;
  italic: boolean;
  boxed: boolean;
  outlinePx: number;
  fontFamily: string;
  textColor: string;
  outlineColor: string;
  backgroundColor: string;
  backgroundOpacity: number;
}

export interface CaptionStyleMeta {
  value: CaptionStyle;
  label: string;
  description: string;
  baseTheme: Omit<
    CaptionStyleTheme,
    "textColor" | "outlineColor" | "backgroundColor" | "backgroundOpacity"
  >;
  baseBackgroundOpacity: number;
  fontSizeOffsetPx: number;
}

export interface CaptionColorVariantMeta {
  value: CaptionColorVariant;
  label: string;
  description: string;
  swatch: {
    textColor: string;
    outlineColor: string;
    backgroundColor: string;
  };
}

const CAPTION_STYLE_META: CaptionStyleMeta[] = [
  {
    value: "bold_boxed",
    label: "Bold Boxed",
    description: "High-contrast boxed text for quick readability.",
    baseTheme: {
      bold: true,
      italic: false,
      boxed: true,
      outlinePx: 1,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.62,
    fontSizeOffsetPx: 3,
  },
  {
    value: "sermon_quote",
    label: "Sermon Quote",
    description: "Italic quote style for reflective speaking clips.",
    baseTheme: {
      bold: false,
      italic: true,
      boxed: false,
      outlinePx: 2,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.35,
    fontSizeOffsetPx: 1,
  },
  {
    value: "clean_minimal",
    label: "Clean Minimal",
    description: "Simple low-noise subtitle style.",
    baseTheme: {
      bold: false,
      italic: false,
      boxed: false,
      outlinePx: 1.5,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.28,
    fontSizeOffsetPx: 0,
  },
  {
    value: "kinetic_bold",
    label: "Kinetic Bold",
    description: "Punchy bold blocks with extra emphasis.",
    baseTheme: {
      bold: true,
      italic: false,
      boxed: true,
      outlinePx: 0.8,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.72,
    fontSizeOffsetPx: 5,
  },
  {
    value: "cinema_outline",
    label: "Cinema Outline",
    description: "Cinematic outlined text with minimal backdrop.",
    baseTheme: {
      bold: true,
      italic: false,
      boxed: false,
      outlinePx: 3,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.12,
    fontSizeOffsetPx: 2,
  },
  {
    value: "clean_highlight",
    label: "Clean Highlight",
    description: "Clean style with a subtle highlight bar.",
    baseTheme: {
      bold: false,
      italic: false,
      boxed: true,
      outlinePx: 0.6,
      fontFamily: "Arial, Helvetica, sans-serif",
    },
    baseBackgroundOpacity: 0.45,
    fontSizeOffsetPx: 1,
  },
];

const CAPTION_COLOR_VARIANTS: CaptionColorVariantMeta[] = [
  {
    value: "classic",
    label: "Classic",
    description: "Neutral white text with dark contrast.",
    swatch: {
      textColor: "#ffffff",
      outlineColor: "#141414",
      backgroundColor: "#000000",
    },
  },
  {
    value: "warm",
    label: "Warm",
    description: "Softer amber-tinted text for warm scenes.",
    swatch: {
      textColor: "#ffeec4",
      outlineColor: "#3a2b1d",
      backgroundColor: "#3f2200",
    },
  },
  {
    value: "cool",
    label: "Cool",
    description: "Crisp blue-tinted text for cool-toned footage.",
    swatch: {
      textColor: "#daf2ff",
      outlineColor: "#1a2f41",
      backgroundColor: "#001f3d",
    },
  },
];

const CAPTION_STYLE_COLOR_PALETTE: Record<
  CaptionStyle,
  Record<
    CaptionColorVariant,
    {
      textColor: string;
      outlineColor: string;
      backgroundColor: string;
      backgroundOpacity?: number;
    }
  >
> = {
  bold_boxed: {
    classic: { textColor: "#ffffff", outlineColor: "#141414", backgroundColor: "#000000", backgroundOpacity: 0.62 },
    warm: { textColor: "#fff8cc", outlineColor: "#332012", backgroundColor: "#442200", backgroundOpacity: 0.62 },
    cool: { textColor: "#e6f6ff", outlineColor: "#1a2f45", backgroundColor: "#001f40", backgroundOpacity: 0.62 },
  },
  sermon_quote: {
    classic: { textColor: "#f5f5f5", outlineColor: "#202020", backgroundColor: "#000000", backgroundOpacity: 0.35 },
    warm: { textColor: "#fff4dc", outlineColor: "#342516", backgroundColor: "#3b1f00", backgroundOpacity: 0.35 },
    cool: { textColor: "#e8f5ff", outlineColor: "#1a3044", backgroundColor: "#001a33", backgroundOpacity: 0.35 },
  },
  clean_minimal: {
    classic: { textColor: "#ffffff", outlineColor: "#141414", backgroundColor: "#000000", backgroundOpacity: 0.28 },
    warm: { textColor: "#fff6e4", outlineColor: "#362616", backgroundColor: "#3b1d00", backgroundOpacity: 0.28 },
    cool: { textColor: "#e9f7ff", outlineColor: "#1b2f43", backgroundColor: "#001c39", backgroundOpacity: 0.28 },
  },
  kinetic_bold: {
    classic: { textColor: "#ffffff", outlineColor: "#0e0e0e", backgroundColor: "#000000", backgroundOpacity: 0.72 },
    warm: { textColor: "#fff3cc", outlineColor: "#392511", backgroundColor: "#4c2300", backgroundOpacity: 0.72 },
    cool: { textColor: "#ddf2ff", outlineColor: "#152d45", backgroundColor: "#001f49", backgroundOpacity: 0.72 },
  },
  cinema_outline: {
    classic: { textColor: "#ffffff", outlineColor: "#0a0a0a", backgroundColor: "#000000", backgroundOpacity: 0.12 },
    warm: { textColor: "#fff2d8", outlineColor: "#3b2818", backgroundColor: "#341c00", backgroundOpacity: 0.16 },
    cool: { textColor: "#e5f3ff", outlineColor: "#152a3f", backgroundColor: "#00182f", backgroundOpacity: 0.16 },
  },
  clean_highlight: {
    classic: { textColor: "#ffffff", outlineColor: "#141414", backgroundColor: "#000000", backgroundOpacity: 0.45 },
    warm: { textColor: "#fff3dc", outlineColor: "#352413", backgroundColor: "#422100", backgroundOpacity: 0.45 },
    cool: { textColor: "#e4f4ff", outlineColor: "#193045", backgroundColor: "#001d3a", backgroundOpacity: 0.45 },
  },
};

const STYLE_META_BY_VALUE: Record<CaptionStyle, CaptionStyleMeta> = Object.fromEntries(
  CAPTION_STYLE_META.map((item) => [item.value, item])
) as Record<CaptionStyle, CaptionStyleMeta>;

const COLOR_VARIANT_META_BY_VALUE: Record<CaptionColorVariant, CaptionColorVariantMeta> = Object.fromEntries(
  CAPTION_COLOR_VARIANTS.map((item) => [item.value, item])
) as Record<CaptionColorVariant, CaptionColorVariantMeta>;

export function getCaptionStyleOptions(): CaptionStyleMeta[] {
  return CAPTION_STYLE_META;
}

export function getCaptionStyleMeta(captionStyle: CaptionStyle): CaptionStyleMeta {
  return STYLE_META_BY_VALUE[captionStyle] || STYLE_META_BY_VALUE.clean_minimal;
}

export function getCaptionColorVariantOptions(): CaptionColorVariantMeta[] {
  return CAPTION_COLOR_VARIANTS;
}

export function getCaptionColorVariantMeta(
  captionColorVariant: CaptionColorVariant | null | undefined
): CaptionColorVariantMeta {
  if (!captionColorVariant) return COLOR_VARIANT_META_BY_VALUE.classic;
  return COLOR_VARIANT_META_BY_VALUE[captionColorVariant] || COLOR_VARIANT_META_BY_VALUE.classic;
}

export function formatCaptionStyleLabel(captionStyle: CaptionStyle | null | undefined): string {
  if (!captionStyle) return "No style";
  return getCaptionStyleMeta(captionStyle).label;
}

export function formatCaptionColorVariantLabel(
  captionColorVariant: CaptionColorVariant | null | undefined
): string {
  return getCaptionColorVariantMeta(captionColorVariant).label;
}

export function getCaptionPreviewLayout(
  captionStyle: CaptionStyle,
  aspectRatio: AspectRatio,
  sourceAspectRatio?: number | null
): CaptionPreviewLayout {
  const effectiveAspect =
    aspectRatio === "original"
      ? sourceAspectRatio && sourceAspectRatio < 0.92
        ? "9:16"
        : sourceAspectRatio && sourceAspectRatio > 1.08
          ? "16:9"
          : "1:1"
      : aspectRatio;

  const styleMeta = getCaptionStyleMeta(captionStyle);

  if (effectiveAspect === "9:16") {
    return {
      fontSizePx: 23 + styleMeta.fontSizeOffsetPx,
      lineHeight: 1.22,
      marginXPercent: 12,
      marginBottomPercent: 15,
      maxCharsPerLine: 20,
      maxLines: 3,
    };
  }

  if (effectiveAspect === "16:9") {
    return {
      fontSizePx: 29 + styleMeta.fontSizeOffsetPx,
      lineHeight: 1.2,
      marginXPercent: 8,
      marginBottomPercent: 11,
      maxCharsPerLine: 34,
      maxLines: 3,
    };
  }

  return {
    fontSizePx: 31 + styleMeta.fontSizeOffsetPx,
    lineHeight: 1.22,
    marginXPercent: 10,
    marginBottomPercent: 12,
    maxCharsPerLine: 28,
    maxLines: 3,
  };
}

export function getCaptionStyleTheme(
  captionStyle: CaptionStyle,
  captionColorVariant: CaptionColorVariant | null | undefined
): CaptionStyleTheme {
  const styleMeta = getCaptionStyleMeta(captionStyle);
  const resolvedVariant = getCaptionColorVariantMeta(captionColorVariant).value;
  const variantPalette =
    CAPTION_STYLE_COLOR_PALETTE[captionStyle]?.[resolvedVariant] ||
    CAPTION_STYLE_COLOR_PALETTE.clean_minimal.classic;
  return {
    ...styleMeta.baseTheme,
    textColor: variantPalette.textColor,
    outlineColor: variantPalette.outlineColor,
    backgroundColor: variantPalette.backgroundColor,
    backgroundOpacity: variantPalette.backgroundOpacity ?? styleMeta.baseBackgroundOpacity,
  };
}

export function wrapCaptionPreviewText(
  text: string,
  maxCharsPerLine: number,
  maxLines: number
): string[] {
  const words = text
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (!words.length) return [];

  const lines: string[] = [];
  let current = "";
  let idx = 0;

  while (idx < words.length && lines.length < maxLines) {
    const word = words[idx];
    const next = current ? `${current} ${word}` : word;
    if (current && next.length > maxCharsPerLine) {
      lines.push(current);
      current = "";
      continue;
    }
    current = next;
    idx += 1;
  }

  if (current && lines.length < maxLines) {
    lines.push(current);
  }

  if (idx < words.length && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].replace(/[.,!?;:]+$/, "")}...`;
  }

  return lines.slice(0, maxLines);
}

export function buildCaptionPreviewText(transcriptText: string | null): string {
  const source = (transcriptText || "").replace(/\s+/g, " ").trim();
  if (!source) {
    return "Your caption preview appears here after transcript text is available.";
  }

  const words = source.split(" ");
  return words.slice(0, 22).join(" ");
}
