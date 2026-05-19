from app.models.video import ClipProfile
from app.schemas.video import VideoImportYoutubeRequest, VideoUploadUrlRequest
from app.services.scoring import (
    CandidateWindow,
    calculate_hook_score,
    get_clip_selection_profile,
    select_top_candidates,
)


def test_clip_profile_defaults_to_viral():
    profile = get_clip_selection_profile(None)
    assert profile.clip_profile == ClipProfile.viral
    assert profile.min_duration_sec == 15.0
    assert profile.max_duration_sec == 40.0
    assert profile.top_n == 10


def test_sermon_clip_profile_values():
    profile = get_clip_selection_profile("sermon")
    assert profile.clip_profile == ClipProfile.sermon
    assert profile.min_duration_sec == 60.0
    assert profile.max_duration_sec == 180.0
    assert profile.min_words == 90
    assert profile.top_n == 12
    assert profile.pause_gap_sec == 2.0
    assert profile.chunk_merge_gap_sec == 3.0
    assert profile.hook_weight == 0.45
    assert profile.energy_weight == 0.55
    assert profile.hook_word_bonus_max == 340


def test_sermon_hook_bonus_handles_longer_windows():
    transcript_text = "listen " + " ".join(f"word{i}" for i in range(150))
    viral_score = calculate_hook_score(transcript_text, start_time=12.0)
    sermon_score = calculate_hook_score(
        transcript_text,
        start_time=12.0,
        hook_word_bonus_min=50,
        hook_word_bonus_max=340,
    )
    assert sermon_score > viral_score


def test_long_form_speaking_alias_maps_to_sermon_profile():
    profile = get_clip_selection_profile("long_form_speaking")
    assert profile.clip_profile == ClipProfile.sermon
    assert profile.min_duration_sec == 60.0
    assert profile.max_duration_sec == 180.0


def test_request_models_accept_long_form_speaking_alias():
    upload_request = VideoUploadUrlRequest(
        filename="example.mp4",
        file_size=1024,
        content_type="video/mp4",
        clip_profile="long_form_speaking",
    )
    import_request = VideoImportYoutubeRequest(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        clip_profile="long_form_speaking",
    )
    assert upload_request.clip_profile == ClipProfile.sermon
    assert import_request.clip_profile == ClipProfile.sermon


def _make_candidate(start: float, duration: float, score: float) -> CandidateWindow:
    return CandidateWindow(
        start=start,
        end=start + duration,
        transcript_text=f"window-{start}",
        hook_score=score,
        energy_score=score,
        combined_score=score,
    )


def _duration_band(duration: float) -> str:
    if duration <= 90.0:
        return "short"
    if duration <= 130.0:
        return "medium"
    return "long"


def test_sermon_balanced_selector_prefers_6_4_2_duration_mix_when_available():
    candidates: list[CandidateWindow] = []

    # 8 high-scoring short windows
    for idx in range(8):
        candidates.append(_make_candidate(start=idx * 300.0, duration=80.0, score=1.00 - (idx * 0.01)))

    # 6 medium windows
    for idx in range(6):
        candidates.append(
            _make_candidate(start=5000.0 + (idx * 300.0), duration=110.0, score=0.92 - (idx * 0.01))
        )

    # 4 long windows
    for idx in range(4):
        candidates.append(
            _make_candidate(start=9000.0 + (idx * 300.0), duration=150.0, score=0.86 - (idx * 0.01))
        )

    selected = select_top_candidates(
        candidates=candidates,
        top_n=12,
        max_overlap_ratio=0.70,
        clip_profile=ClipProfile.sermon,
    )

    assert len(selected) == 12
    bands = {"short": 0, "medium": 0, "long": 0}
    for candidate in selected:
        bands[_duration_band(candidate.duration)] += 1

    assert bands == {"short": 6, "medium": 4, "long": 2}


def test_sermon_balanced_selector_fills_from_remaining_when_bands_are_missing():
    candidates: list[CandidateWindow] = []

    for idx in range(14):
        candidates.append(_make_candidate(start=idx * 200.0, duration=85.0, score=1.00 - (idx * 0.01)))
    candidates.append(_make_candidate(start=5000.0, duration=120.0, score=0.30))

    selected = select_top_candidates(
        candidates=candidates,
        top_n=12,
        max_overlap_ratio=0.70,
        clip_profile=ClipProfile.sermon,
    )

    assert len(selected) == 12
    medium_count = sum(1 for candidate in selected if _duration_band(candidate.duration) == "medium")
    long_count = sum(1 for candidate in selected if _duration_band(candidate.duration) == "long")
    assert medium_count == 1
    assert long_count == 0


def test_sermon_balanced_selector_still_respects_overlap_rules():
    primary_short = _make_candidate(start=0.0, duration=80.0, score=1.00)
    overlapping_short = _make_candidate(start=10.0, duration=80.0, score=0.99)
    medium = _make_candidate(start=220.0, duration=110.0, score=0.80)
    long = _make_candidate(start=500.0, duration=150.0, score=0.70)

    selected = select_top_candidates(
        candidates=[primary_short, overlapping_short, medium, long],
        top_n=3,
        max_overlap_ratio=0.70,
        clip_profile=ClipProfile.sermon,
    )

    assert primary_short in selected
    assert overlapping_short not in selected
    assert len(selected) == 3
