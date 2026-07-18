# Production Notes

This file records production issues that were difficult enough to justify keeping the root cause and recovery path close to the codebase.

## 001. Editor preview played audio but showed black video

The advanced clip editor originally used the source media directly inside a transformed preview canvas. Some uploads carried HDR or HLG metadata, including BT.2020 color information, and those files could advance audio while Chrome failed to paint visible frames in the editor. The basic video page was more tolerant, which made the issue look like a UI sizing problem at first.

The durable fix was to separate editor preview compatibility from final export quality. PostBandit now generates browser-safe preview media for editor playback while keeping final renders on the original source file. Preview files are encoded as H.264/AAC with `yuv420p`, BT.709 output, constant frame rate, frequent keyframes, and faststart metadata. HDR-like sources require real tone mapping; metadata retagging alone is not enough.

The frontend also stopped opening automatic fallback tabs from normal playback controls. If preview generation fails, the editor should show an explicit recovery state instead of creating a confusing browser popup.

When this class of issue appears again, check the source and preview with `ffprobe`, verify the stored preview status and profile version, and inspect worker logs for preview generation failures. A valid editor preview should report non-zero video dimensions in the browser and should show visible frames while audio plays.

Operational rule: preview media is compatibility-focused; final export media is quality-focused. Keep those paths separate.
