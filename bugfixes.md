# Bug Fixes Log

This file tracks major production issues, root causes, and proven fixes.

## 001) Clip Editor shows audio only (black video preview)

### Summary
In the new editor route, video playback advanced and audio played, but no visible frames rendered in the preview canvas.

### Symptoms
- Editor timeline/playhead moved normally.
- Audio played in the editor.
- Preview area stayed black.
- In some fallback states, clicking play could open an unhelpful blank tab.

### Root Cause
This was a combination issue:

1. **Source media HDR/HLG characteristics**
   - Problem videos had HDR-like metadata (`bt2020nc`, `arib-std-b67`).
   - Browser decode/paint behavior was unstable in the editor path.

2. **Proxy conversion was initially metadata retagging, not true tone-mapping**
   - Early proxy path forced BT.709 tags but did not fully perform HDR -> SDR tone mapping.
   - That can still produce poor/blank visual output in browser playback paths.

3. **Editor preview path fragility**
   - The new editor rendering path was less tolerant than older preview flow.
   - Auto-fallback popup behavior added noise during debugging.

### What fixed it

1. **Durable editor proxy pipeline upgrade**
   - Added real HDR -> SDR conversion in preview proxy generatio n.
   - Enforced browser-safe output (H.264/AAC, yuv420p, BT.709, CFR, faststart).
   - Added preview profile versioning so stale proxies are regenerated with the new pipeline.

2. **Editor frontend stabilization**
   - Simplified preview to a more stable direct `<video>` rendering path.
   - Removed auto-open fallback popup behavior from normal play flow.

3. **Operational validation**
   - Confirmed worker task progression and completion.
   - Confirmed DB metadata transitions (`pending -> ready`) for preview.
   - Rechecked stream details with `ffprobe`.

### Verified fix checklist
- [ ] `editor_preview_status` becomes `ready`.
- [ ] `editor_preview_profile_version` matches current profile version.
- [ ] Editor debug strip shows non-zero video dimensions.
- [ ] Editor preview displays visible frames while audio plays.

### If this happens again

1. Check video metadata and proxy status in DB:
   - `editor_preview_status`
   - `editor_preview_key`
   - `editor_preview_profile_version`
2. Check worker logs for `editor_preview_proxy_*` events.
3. `ffprobe` source and proxy files:
   - codec/pix_fmt/colorspace/transfer/primaries
4. If proxy pipeline changed, force regenerate preview for that video.
5. Hard-refresh editor and re-test.

### Preventive notes
- Keep editor proxy generation as a required compatibility step for HDR-like uploads.
- Do not rely on color metadata retagging alone for HDR sources.
- Keep preview and render pipelines separated:
  - Preview = compatibility-focused
  - Final export = quality-focused (server FFmpeg pipeline)
- Durable follow-up: editor preview should use a project/clip-window proxy, not the full source video.
- Normal editor playback controls must never auto-open fallback tabs; use explicit regenerate/retry actions instead.
- Store preview readiness on the editor project so autosave and playback are tied to the exact clip window being edited.

---

## Incident Template

Copy this section for each new major bug:

```md
## <INCIDENT_ID>) <Short bug title>

### Summary
<1-2 lines on impact and where it appeared>

### Symptoms
- <observable symptom 1>
- <observable symptom 2>
- <observable symptom 3>

### Root Cause
1. <primary cause>
2. <secondary cause, if any>
3. <system/design contributor, if any>

### What fixed it
1. <code or config fix #1>
2. <code or config fix #2>
3. <operational/deploy fix #3>

### Verified fix checklist
- [ ] <verification item 1>
- [ ] <verification item 2>
- [ ] <verification item 3>

### If this happens again
1. <debug step 1>
2. <debug step 2>
3. <debug step 3>

### Preventive notes
- <prevention note 1>
- <prevention note 2>
- <prevention note 3>

### References
- Commit(s): `<sha>`
- Files touched: `<path1>`, `<path2>`
- Environment(s): <local/vps/prod>
- Date resolved: <YYYY-MM-DD>
```
