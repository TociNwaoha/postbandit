import audioop
import math
import re
import wave
from dataclasses import dataclass

from app.models.exclude_zone import ExcludeZone
from app.models.transcript import TranscriptSegment
from app.models.video import ClipProfile

LONG_FORM_CLIP_PROFILE_ALIASES = {"long_form_speaking"}


TERMINAL_PUNCTUATION_RE = re.compile(r"[.!?][\"')\]]*$")

HOOK_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(you need to|you must|don['’]t)\b"), 0.18),
    (re.compile(r"\b(here['’]s|this is) (why|how|what)\b"), 0.18),
    (re.compile(r"\b(what if|imagine|listen)\b"), 0.14),
    (re.compile(r"\b(secret|mistake|truth|powerful|important)\b"), 0.13),
    (re.compile(r"\b(how to|steps|strategy)\b"), 0.12),
]

OPENING_PHRASES = (
    "today ",
    "so ",
    "listen ",
    "imagine ",
    "what if ",
    "here's ",
    "here’s ",
)


@dataclass(frozen=True)
class WordToken:
    word: str
    start: float
    end: float


@dataclass(frozen=True)
class CandidateWindow:
    start: float
    end: float
    transcript_text: str
    hook_score: float
    energy_score: float
    combined_score: float

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)


@dataclass(frozen=True)
class Chunk:
    start: float
    end: float
    tokens: list[WordToken]

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 0.0)


@dataclass(frozen=True)
class AudioEnergyProfile:
    buckets: list[float]
    bucket_size_sec: float
    p10: float
    p90: float


@dataclass(frozen=True)
class ClipSelectionProfile:
    clip_profile: ClipProfile
    min_duration_sec: float
    max_duration_sec: float
    min_words: int
    top_n: int
    max_overlap_ratio: float
    pause_gap_sec: float
    chunk_merge_gap_sec: float
    hook_weight: float
    energy_weight: float
    hook_word_bonus_min: int
    hook_word_bonus_max: int


CLIP_SELECTION_PROFILES: dict[ClipProfile, ClipSelectionProfile] = {
    ClipProfile.viral: ClipSelectionProfile(
        clip_profile=ClipProfile.viral,
        min_duration_sec=15.0,
        max_duration_sec=40.0,
        min_words=20,
        top_n=10,
        max_overlap_ratio=0.55,
        pause_gap_sec=1.0,
        chunk_merge_gap_sec=1.5,
        hook_weight=0.65,
        energy_weight=0.35,
        hook_word_bonus_min=25,
        hook_word_bonus_max=110,
    ),
    ClipProfile.sermon: ClipSelectionProfile(
        clip_profile=ClipProfile.sermon,
        min_duration_sec=60.0,
        max_duration_sec=180.0,
        min_words=90,
        top_n=12,
        max_overlap_ratio=0.70,
        pause_gap_sec=2.0,
        chunk_merge_gap_sec=3.0,
        hook_weight=0.45,
        energy_weight=0.55,
        hook_word_bonus_min=50,
        hook_word_bonus_max=340,
    ),
}


def get_clip_selection_profile(profile_value: str | ClipProfile | None) -> ClipSelectionProfile:
    if isinstance(profile_value, ClipProfile):
        return CLIP_SELECTION_PROFILES.get(profile_value, CLIP_SELECTION_PROFILES[ClipProfile.viral])

    if isinstance(profile_value, str):
        normalized = profile_value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized == ClipProfile.sermon.value or normalized in LONG_FORM_CLIP_PROFILE_ALIASES:
            return CLIP_SELECTION_PROFILES[ClipProfile.sermon]

    return CLIP_SELECTION_PROFILES[ClipProfile.viral]


def build_word_tokens(segments: list[TranscriptSegment]) -> list[WordToken]:
    tokens: list[WordToken] = []
    for segment in segments:
        token = (segment.word or "").strip()
        if not token:
            continue
        start = float(segment.start_time or 0.0)
        end = float(segment.end_time or start)
        if end <= start:
            end = start + 0.01
        tokens.append(WordToken(word=token, start=start, end=end))
    tokens.sort(key=lambda item: (item.start, item.end))
    return tokens


def build_chunks(tokens: list[WordToken], pause_gap_sec: float) -> list[Chunk]:
    if not tokens:
        return []

    chunks: list[Chunk] = []
    current: list[WordToken] = [tokens[0]]
    for token in tokens[1:]:
        prev = current[-1]
        gap = token.start - prev.end
        punct_break = bool(TERMINAL_PUNCTUATION_RE.search(prev.word.strip()))

        if gap > pause_gap_sec or punct_break:
            chunks.append(Chunk(start=current[0].start, end=current[-1].end, tokens=list(current)))
            current = [token]
        else:
            current.append(token)

    if current:
        chunks.append(Chunk(start=current[0].start, end=current[-1].end, tokens=list(current)))
    return chunks


def generate_candidate_ranges(
    chunks: list[Chunk],
    tokens: list[WordToken],
    min_duration_sec: float,
    max_duration_sec: float,
    min_words: int,
    chunk_merge_gap_sec: float = 1.5,
) -> list[tuple[float, float]]:
    ranges: list[tuple[float, float]] = []

    for i in range(len(chunks)):
        start = chunks[i].start
        merged_tokens: list[WordToken] = []
        for j in range(i, len(chunks)):
            if j > i and chunks[j].start - chunks[j - 1].end > chunk_merge_gap_sec:
                break

            merged_tokens.extend(chunks[j].tokens)
            end = chunks[j].end
            duration = end - start
            if duration > max_duration_sec:
                break
            if duration >= min_duration_sec and len(merged_tokens) >= min_words:
                ranges.append((start, end))

    if ranges:
        return _dedupe_ranges(ranges)

    # Fallback for long uninterrupted speech where punctuation chunking yields no 15-40s windows.
    step = max(1, min_words // 2)
    for i in range(0, len(tokens), step):
        start = tokens[i].start
        j = i
        while j < len(tokens) and tokens[j].end - start < min_duration_sec:
            j += 1
        if j >= len(tokens):
            break

        best_j = j
        while best_j + 1 < len(tokens) and tokens[best_j + 1].end - start <= max_duration_sec:
            best_j += 1

        if best_j >= i and len(tokens[i:best_j + 1]) >= min_words:
            ranges.append((start, tokens[best_j].end))

    return _dedupe_ranges(ranges)


def apply_exclude_zones(
    start: float,
    end: float,
    zones: list[ExcludeZone],
    min_duration_sec: float,
) -> tuple[float, float] | None:
    segments = [(start, end)]
    for zone in zones:
        zone_start = float(zone.start_time or 0.0)
        zone_end = float(zone.end_time or zone_start)
        if zone_end <= zone_start:
            continue

        next_segments: list[tuple[float, float]] = []
        for seg_start, seg_end in segments:
            if zone_end <= seg_start or zone_start >= seg_end:
                next_segments.append((seg_start, seg_end))
                continue
            if zone_start > seg_start:
                next_segments.append((seg_start, min(zone_start, seg_end)))
            if zone_end < seg_end:
                next_segments.append((max(zone_end, seg_start), seg_end))
        segments = next_segments
        if not segments:
            return None

    longest = max(segments, key=lambda value: value[1] - value[0], default=None)
    if longest is None:
        return None
    if longest[1] - longest[0] < min_duration_sec:
        return None
    return longest


def extract_window_text(tokens: list[WordToken], start: float, end: float) -> str:
    parts = [
        token.word
        for token in tokens
        if token.end > start and token.start < end
    ]
    if not parts:
        return ""
    text = " ".join(parts)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip()


def calculate_hook_score(
    text: str,
    start_time: float,
    hook_word_bonus_min: int = 25,
    hook_word_bonus_max: int = 110,
) -> float:
    if not text:
        return 0.0

    lowered = text.lower()
    score = 0.0

    if "?" in text:
        score += 0.20
    if start_time <= 30:
        score += 0.08
    if lowered.startswith(OPENING_PHRASES):
        score += 0.12

    for pattern, weight in HOOK_PATTERNS:
        if pattern.search(lowered):
            score += weight

    word_count = len(lowered.split())
    min_words = min(hook_word_bonus_min, hook_word_bonus_max)
    max_words = max(hook_word_bonus_min, hook_word_bonus_max)
    if min_words <= word_count <= max_words:
        score += 0.08

    return round(max(0.0, min(score, 1.0)), 4)


def build_energy_profile(audio_path: str, bucket_size_sec: float) -> AudioEnergyProfile:
    buckets: list[float] = []
    with wave.open(audio_path, "rb") as audio_file:
        sample_rate = audio_file.getframerate()
        sample_width = audio_file.getsampwidth()
        channels = max(audio_file.getnchannels(), 1)

        frames_per_bucket = max(1, int(sample_rate * bucket_size_sec))
        bytes_per_bucket = frames_per_bucket * sample_width * channels

        while True:
            raw = audio_file.readframes(frames_per_bucket)
            if not raw:
                break
            if len(raw) < bytes_per_bucket:
                raw = raw + b"\x00" * (bytes_per_bucket - len(raw))
            rms = audioop.rms(raw, sample_width)
            max_value = float((2 ** (8 * sample_width - 1)) - 1)
            buckets.append(rms / max_value if max_value else 0.0)

    if not buckets:
        buckets = [0.0]

    p10 = _percentile(buckets, 0.10)
    p90 = _percentile(buckets, 0.90)
    if math.isclose(p10, p90):
        p90 = p10 + 1e-6

    return AudioEnergyProfile(
        buckets=buckets,
        bucket_size_sec=bucket_size_sec,
        p10=p10,
        p90=p90,
    )


def calculate_energy_score(
    start: float,
    end: float,
    profile: AudioEnergyProfile,
) -> float:
    if end <= start:
        return 0.0

    start_idx = max(0, int(math.floor(start / profile.bucket_size_sec)))
    end_idx = min(len(profile.buckets), int(math.ceil(end / profile.bucket_size_sec)))
    if end_idx <= start_idx:
        end_idx = min(len(profile.buckets), start_idx + 1)

    bucket_slice = profile.buckets[start_idx:end_idx] or [0.0]
    average = sum(bucket_slice) / len(bucket_slice)
    normalized = (average - profile.p10) / (profile.p90 - profile.p10)
    return round(max(0.0, min(normalized, 1.0)), 4)


def select_top_candidates(
    candidates: list[CandidateWindow],
    top_n: int,
    max_overlap_ratio: float,
    clip_profile: ClipProfile = ClipProfile.viral,
) -> list[CandidateWindow]:
    ranked = sorted(
        candidates,
        key=lambda item: (item.combined_score, item.hook_score, item.energy_score, item.duration),
        reverse=True,
    )

    if clip_profile != ClipProfile.sermon:
        selected: list[CandidateWindow] = []
        for candidate in ranked:
            if _has_too_much_overlap(candidate, selected, max_overlap_ratio):
                continue
            selected.append(candidate)
            if len(selected) >= top_n:
                break
        return selected

    def _duration_band(duration: float) -> str:
        if duration <= 90.0:
            return "short"
        if duration <= 130.0:
            return "medium"
        return "long"

    band_targets = {"short": 6, "medium": 4, "long": 2}
    band_counts = {key: 0 for key in band_targets}
    selected: list[CandidateWindow] = []

    # Pass 1: enforce a balanced duration mix for long-form profile.
    for candidate in ranked:
        band = _duration_band(candidate.duration)
        if band_counts[band] >= band_targets[band]:
            continue
        if _has_too_much_overlap(candidate, selected, max_overlap_ratio):
            continue
        selected.append(candidate)
        band_counts[band] += 1
        if len(selected) >= top_n:
            return selected

    # Pass 2: fill remaining slots by score regardless of band.
    for candidate in ranked:
        if candidate in selected:
            continue
        if _has_too_much_overlap(candidate, selected, max_overlap_ratio):
            continue
        selected.append(candidate)
        if len(selected) >= top_n:
            break

    return selected


def _dedupe_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    seen: set[tuple[float, float]] = set()
    deduped: list[tuple[float, float]] = []
    for start, end in ranges:
        key = (round(start, 2), round(end, 2))
        if key in seen:
            continue
        seen.add(key)
        deduped.append((start, end))
    return deduped


def _has_too_much_overlap(
    candidate: CandidateWindow,
    selected: list[CandidateWindow],
    max_overlap_ratio: float,
) -> bool:
    for existing in selected:
        overlap_start = max(candidate.start, existing.start)
        overlap_end = min(candidate.end, existing.end)
        overlap = max(0.0, overlap_end - overlap_start)
        if overlap <= 0:
            continue
        denominator = min(candidate.duration, existing.duration)
        if denominator <= 0:
            continue
        overlap_ratio = overlap / denominator
        if overlap_ratio > max_overlap_ratio:
            return True
    return False


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * percentile
    lower_idx = int(math.floor(index))
    upper_idx = int(math.ceil(index))
    if lower_idx == upper_idx:
        return sorted_values[lower_idx]
    lower_value = sorted_values[lower_idx]
    upper_value = sorted_values[upper_idx]
    fraction = index - lower_idx
    return lower_value + (upper_value - lower_value) * fraction
