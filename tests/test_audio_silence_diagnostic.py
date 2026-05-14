"""Regression tests for the one-shot silent-microphone diagnostic in ``receive()``.

Traceability
------------
- Behavior introduced by commit ``e36cded`` (2026-05-14):
  "fix: media-backend fallback chain + audio frame/VAD robustness".
  Specifically the squashed portion originating from the patch
  ``0010-fix-flatten-mono-audio-to-1-D-add-silence-check-lowe.patch``
  that adds the ``_audio_silence_checked`` one-shot guard around the
  first-frame peak inspection.
- Specification anchored in commit ``e695e72`` (2026-05-14):
  see ``spec/specs/conversation-and-backends.md``, Requirement
  "Silent-Microphone Diagnostic Warning", with the inline traceability
  tag ``(2026-05-14, e36cded)``.

Coverage matrix
---------------
- P2b.1: first frame with ``peak == 0`` emits exactly one warning whose
  message names the microphone-permission cause.
- P2b.2: first frame with ``peak > 0`` emits exactly one info line that
  reports the peak as non-silent.
- P2b.3: two independent handler instances each run their own one-shot
  check (the flag is instance-scoped, not class-scoped).
- N2b.1: idempotence — if the first frame is silent and many subsequent
  frames are also silent, the warning is emitted exactly once total.
- N2b.2: if the first frame is non-silent (info logged) and later frames
  are silent, no warning is emitted for those later silent frames.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from reachy_mini_conversation_app.openai_realtime import OpenaiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

LOGGER_NAME = "reachy_mini_conversation_app.base_realtime"


@pytest.fixture
def loop():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        yield new_loop
    finally:
        new_loop.close()


def _make_handler() -> OpenaiRealtimeHandler:
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    h = OpenaiRealtimeHandler(deps)
    connection = MagicMock()
    connection.input_audio_buffer = MagicMock()
    connection.input_audio_buffer.append = AsyncMock()
    h.connection = connection
    return h


def _run(loop: asyncio.AbstractEventLoop, coro):
    return loop.run_until_complete(coro)


def _records(caplog, level, substring):
    return [
        r for r in caplog.records
        if r.levelno == level and r.name == LOGGER_NAME and substring in r.getMessage()
    ]


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_p2b_1_silent_first_frame_emits_one_warning(loop, caplog):
    """P2b.1: First frame with peak=0 emits exactly one warning, mentioning

    browser microphone permissions and device selection.
    """
    handler = _make_handler()
    silent = np.zeros(960, dtype=np.int16)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _run(loop, handler.receive((handler.input_sample_rate, silent)))

    warnings = _records(caplog, logging.WARNING, "peak=0")
    assert len(warnings) == 1
    assert "Check browser microphone permissions" in warnings[0].getMessage()


def test_p2b_2_nonsilent_first_frame_emits_one_info(loop, caplog):
    """P2b.2: First frame with peak > 0 emits exactly one info line that

    reports the actual peak amplitude as non-silent.
    """
    handler = _make_handler()
    frame = np.zeros(960, dtype=np.int16)
    frame[42] = 7777

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _run(loop, handler.receive((handler.input_sample_rate, frame)))

    infos = _records(caplog, logging.INFO, "Microphone audio confirmed")
    assert len(infos) == 1
    assert "peak=7777" in infos[0].getMessage()
    assert "non-silent" in infos[0].getMessage()


def test_p2b_3_independent_handler_instances_each_check_once(loop, caplog):
    """P2b.3: ``_audio_silence_checked`` is an instance attribute. Two

    independent handlers must each run their own one-shot check.
    """
    handler_a = _make_handler()
    handler_b = _make_handler()
    silent_a = np.zeros(960, dtype=np.int16)
    silent_b = np.zeros(960, dtype=np.int16)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _run(loop, handler_a.receive((handler_a.input_sample_rate, silent_a)))
        _run(loop, handler_b.receive((handler_b.input_sample_rate, silent_b)))

    warnings = _records(caplog, logging.WARNING, "peak=0")
    assert len(warnings) == 2, "two distinct handler instances should each emit their own warning"


# ---------------------------------------------------------------------------
# Negative / idempotence cases
# ---------------------------------------------------------------------------


def test_n2b_1_silent_first_followed_by_many_silent_frames_warns_only_once(loop, caplog):
    """N2b.1: After the first silent-warning fires, subsequent silent

    frames must not produce additional warnings. The one-shot guard is
    the explicit Spec invariant.
    """
    handler = _make_handler()
    silent = np.zeros(960, dtype=np.int16)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        for _ in range(10):
            _run(loop, handler.receive((handler.input_sample_rate, silent.copy())))

    warnings = _records(caplog, logging.WARNING, "peak=0")
    assert len(warnings) == 1, "warning must fire exactly once across multiple silent frames"


def test_n2b_2_nonsilent_first_then_silent_does_not_warn(loop, caplog):
    """N2b.2: If the first frame was non-silent (info logged, check marked

    done), later silent frames must NOT trigger a warning.
    """
    handler = _make_handler()
    nonsilent = np.zeros(960, dtype=np.int16)
    nonsilent[0] = 12345
    silent = np.zeros(960, dtype=np.int16)

    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        _run(loop, handler.receive((handler.input_sample_rate, nonsilent)))
        for _ in range(5):
            _run(loop, handler.receive((handler.input_sample_rate, silent.copy())))

    warnings = _records(caplog, logging.WARNING, "peak=0")
    assert warnings == [], "warning must not fire after a non-silent first frame"

    infos = _records(caplog, logging.INFO, "Microphone audio confirmed")
    assert len(infos) == 1, "info line must fire exactly once on the first non-silent frame"
