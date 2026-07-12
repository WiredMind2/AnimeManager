"""GPU encoder smoke test (real ffmpeg + local fixture).

Skipped when the SubsPlease Classroom Elite S4E11 file is absent or when
no hardware H.264 encoder is available.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from adapters.media.ffmpeg_encoder import SOFTWARE_ENCODER
from adapters.media.ffmpeg_transcoder import FFmpegTranscoderAdapter

EPISODE_PATH = Path(
    r"C:\Users\willi\Documents\Anime\Animes\Classroom of the Elite 4th Season Second Year First Semester - 1090"
    r"\[SubsPlease] Youkoso Jitsuryoku Shijou Shugi no Kyoushitsu e S4 - 11 (720p) [7CA0682C].mkv"
)

pytestmark = pytest.mark.skipif(
    not EPISODE_PATH.is_file(),
    reason="Local SubsPlease S4E11 fixture is not present on this machine",
)


@pytest.fixture
def gpu_transcoder() -> FFmpegTranscoderAdapter:
    adapter = FFmpegTranscoderAdapter(video_encoder="auto")
    if adapter._video_encoder == SOFTWARE_ENCODER:
        pytest.skip("No hardware H.264 encoder available")
    yield adapter
    adapter.stop_hls_session("gpu-smoke")


@pytest.mark.gpu
def test_gpu_encoder_produces_playable_segment(gpu_transcoder, tmp_path: Path) -> None:
    adapter = gpu_transcoder
    out = tmp_path / "gpu-out"
    adapter.ensure_hls_session(
        session_id="gpu-smoke",
        source_path=str(EPISODE_PATH),
        output_dir=str(out),
        start_segment_index=0,
        segment_seconds=4,
    )

    seg_path: Path | None = None
    deadline = time.monotonic() + 90.0
    while time.monotonic() < deadline:
        segments = sorted(out.glob("segment_*.ts"))
        if segments:
            seg_path = segments[0]
            break
        if not adapter.is_hls_session_running("gpu-smoke"):
            break
        time.sleep(0.5)

    assert seg_path is not None, "ffmpeg did not produce an HLS segment"
    assert seg_path.stat().st_size > 10_000

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,pix_fmt",
            "-of",
            "json",
            str(seg_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    payload = json.loads(probe.stdout or "{}")
    streams = list(payload.get("streams") or [])
    video = next((s for s in streams if s.get("codec_name")), streams[0] if streams else {})
    assert video.get("codec_name") == "h264"
    assert video.get("pix_fmt") == "yuv420p"
    assert adapter.is_hls_session_running("gpu-smoke")
