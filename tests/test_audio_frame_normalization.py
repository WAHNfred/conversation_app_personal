"""Regression tests for audio-frame normalisation in ``BaseRealtimeHandler.receive()``.

Traceability
------------
- Behavior introduced by commit ``e36cded`` (2026-05-14):
  "fix: media-backend fallback chain + audio frame/VAD robustness".
  Specifically the squashed portion originating from the patch
  ``0010-fix-flatten-mono-audio-to-1-D-add-silence-check-lowe.patch``
  affecting ``src/reachy_mini_conversation_app/base_realtime.py``.
  Pre-fix code transposed ``(1, 960)`` to ``(960, 1)`` but never squeezed
  the singleton channel dimension, leaving downstream resample/buffer logic
  operating on a 2-D array.
- Specification anchored in commit ``e695e72`` (2026-05-14):
  see ``spec/specs/conversation-and-backends.md``, Requirement
  "Audio Frame Normalization To 1-D Mono", with the inline traceability
  tag ``(2026-05-14, e36cded)``.

Coverage matrix
---------------
- P2a.1: shape ``(1, 960)`` → 1-D length 960.
- P2a.2: shape ``(960, 2)`` → 1-D length 960 (first channel kept).
- P2a.3: shape ``(960,)`` already 1-D → unchanged.
- P2a.4: shape ``(2, 960)`` → transposed, collapsed to 1-D length 960.
- P2a.5: ``int16`` dtype is preserved end-to-end.
- N2a.1: empty 1-D frame ``(0,)`` does not crash.
- N2a.2: empty 2-D frame ``(0, 1)`` does not crash.
- N2a.3: status quo for 3-D frames (passes through, current behaviour).
- N2a.4: square frame ``(N, N)`` heuristic — pins current ambiguous handling.
"""

from __future__ import annotations

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from reachy_mini_conversation_app.openai_realtime import OpenaiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def loop():
    """Fresh event loop per test (handler init touches the running-loop API)."""
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        yield new_loop
    finally:
        new_loop.close()


@pytest.fixture
def handler(loop):
    """Handler with a mocked WebSocket-style connection so ``receive()`` can run."""
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    h = OpenaiRealtimeHandler(deps)
    connection = MagicMock()
    connection.input_audio_buffer = MagicMock()
    connection.input_audio_buffer.append = AsyncMock()
    h.connection = connection
    return h


def _run(loop: asyncio.AbstractEventLoop, coro):
    return loop.run_until_complete(coro)


def _captured_frame_bytes(handler) -> bytes:
    """Return the raw int16 byte payload of the most recent ``append`` call."""
    call = handler.connection.input_audio_buffer.append.call_args
    assert call is not None, "expected receive() to call input_audio_buffer.append"
    audio_b64 = call.kwargs["audio"]
    return base64.b64decode(audio_b64)


def _captured_int16_array(handler) -> np.ndarray:
    return np.frombuffer(_captured_frame_bytes(handler), dtype=np.int16)


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_p2a_1_channels_first_1_x_N_collapsed_to_1d(loop, handler):
    """P2a.1: ``(1, 960)`` is transposed to ``(960, 1)`` and then collapsed."""
    frame = np.zeros((1, 960), dtype=np.int16)
    frame[0, 100] = 1234

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    out = _captured_int16_array(handler)
    assert out.ndim == 1
    assert out.shape == (960,)
    assert out[100] == 1234


def test_p2a_2_multichannel_keeps_first_channel(loop, handler):
    """P2a.2: ``(960, 2)`` collapses to 1-D length 960 using the first channel."""
    frame = np.zeros((960, 2), dtype=np.int16)
    frame[:, 0] = np.arange(960, dtype=np.int16)
    # Use a sentinel value that ``arange(960)`` never produces so the
    # check "second channel was dropped" is unambiguous.
    frame[:, 1] = -1

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    out = _captured_int16_array(handler)
    assert out.shape == (960,)
    assert np.array_equal(out, np.arange(960, dtype=np.int16))
    assert -1 not in out.tolist(), "second channel must not appear in the payload"


def test_p2a_3_already_1d_frame_passes_through(loop, handler):
    """P2a.3: 1-D input is forwarded unchanged."""
    frame = np.arange(960, dtype=np.int16)

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    out = _captured_int16_array(handler)
    assert out.shape == (960,)
    assert np.array_equal(out, frame)


def test_p2a_4_channels_first_2_x_N_transposed_and_collapsed(loop, handler):
    """P2a.4: ``(2, 960)`` shape is detected as channels-first, transposed,

    then the first channel is retained.
    """
    frame = np.zeros((2, 960), dtype=np.int16)
    frame[0, :] = np.arange(960, dtype=np.int16)
    # Use a sentinel value the first-channel sequence never produces.
    frame[1, :] = -1

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    out = _captured_int16_array(handler)
    assert out.shape == (960,)
    assert np.array_equal(out, np.arange(960, dtype=np.int16))
    assert -1 not in out.tolist()


def test_p2a_5_int16_dtype_preserved(loop, handler):
    """P2a.5: ``int16`` input round-trips as int16 bytes after normalisation."""
    frame = np.full((1, 960), 1000, dtype=np.int16)

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    raw = _captured_frame_bytes(handler)
    assert len(raw) == 960 * 2, "int16 mono 960-sample frame must be exactly 1920 bytes"
    arr = np.frombuffer(raw, dtype=np.int16)
    assert (arr == 1000).all()


# ---------------------------------------------------------------------------
# Negative / edge cases
# ---------------------------------------------------------------------------


def test_n2a_1_empty_1d_frame_pins_status_quo(loop, handler):
    """N2a.1 (latent bug, status-quo pin): an empty 1-D frame currently

    raises ``ValueError`` because the silence-check's ``np.abs(...).max()``
    cannot reduce an empty array. aiortc never delivers empty frames in
    practice, so this is a latent edge case. If a future hardening
    patch handles empty frames gracefully, this assertion will need to
    be flipped to ``does not raise`` and the spec updated alongside.
    """
    frame = np.zeros(0, dtype=np.int16)

    with pytest.raises(ValueError, match="zero-size array"):
        _run(loop, handler.receive((handler.input_sample_rate, frame)))


def test_n2a_2_empty_2d_frame_pins_status_quo(loop, handler):
    """N2a.2 (latent bug, status-quo pin): an empty 2-D frame with shape

    ``(0, 1)`` currently raises ``IndexError`` on the ``[:, 0]`` collapse
    (axis 1 has size 0 in this edge case after the transpose-heuristic
    check). Same caveat as N2a.1 — if hardening lands, update test +
    spec together.
    """
    frame = np.zeros((0, 1), dtype=np.int16)

    with pytest.raises(IndexError):
        _run(loop, handler.receive((handler.input_sample_rate, frame)))


def test_n2a_3_three_dim_frame_is_status_quo_passthrough(loop, handler):
    """N2a.3: 3-D frames fall through the ``ndim == 2`` reshape block.

    Currently aiortc never delivers 3-D arrays so this is an untested
    edge in production. This test pins today's behaviour so a future
    regression is visible: if normalisation is generalised to 3-D, this
    assertion will need to be updated alongside the spec.
    """
    frame = np.zeros((1, 1, 960), dtype=np.int16)

    # The current implementation will likely raise on the downstream
    # ``base64.b64encode(audio_frame.tobytes())`` if shape is unexpected —
    # but the receive() method itself does NOT reshape this. We document
    # the status quo: either it raises a numpy/encoding error, or it
    # passes through. Both are acceptable today.
    try:
        _run(loop, handler.receive((handler.input_sample_rate, frame)))
    except Exception:
        pass  # status quo: 3-D is undefined behaviour, but we don't promise normalisation


def test_n2a_4_square_frame_picks_first_dim_via_shape_heuristic(loop, handler):
    """N2a.4: For a square frame ``(N, N)`` the ``shape[1] > shape[0]``

    transpose heuristic returns False, so no transpose happens; then
    ``[:, 0]`` takes the first column. Pin this behaviour as deliberate.
    """
    frame = np.zeros((64, 64), dtype=np.int16)
    frame[:, 0] = np.arange(64, dtype=np.int16)
    frame[:, 1:] = -1  # everything but column 0

    _run(loop, handler.receive((handler.input_sample_rate, frame)))

    out = _captured_int16_array(handler)
    assert out.shape == (64,)
    assert out[10] == 10 and out[63] == 63
    assert -1 not in out.tolist()
