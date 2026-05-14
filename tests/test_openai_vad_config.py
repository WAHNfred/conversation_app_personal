"""Regression tests for OpenAI Realtime server-VAD tuning in the session config.

Traceability
------------
- Behavior introduced by commit ``e36cded`` (2026-05-14):
  "fix: media-backend fallback chain + audio frame/VAD robustness".
  Specifically the squashed portion originating from the patch
  ``0010-fix-flatten-mono-audio-to-1-D-add-silence-check-lowe.patch``
  that replaces ``ServerVad(type="server_vad", interrupt_response=True)``
  with explicit ``threshold``, ``prefix_padding_ms``, and
  ``silence_duration_ms`` values tuned for laptop / desktop microphones.
- Specification anchored in commit ``e695e72`` (2026-05-14):
  see ``spec/specs/conversation-and-backends.md``, Requirement
  "OpenAI Server-VAD Tuning", with the inline traceability tag
  ``(2026-05-14, e36cded)``.

Coverage matrix
---------------
- P3.1: ``turn_detection.threshold == 0.3``.
- P3.2: ``turn_detection.prefix_padding_ms == 300``.
- P3.3: ``turn_detection.silence_duration_ms == 500``.
- P3.4: ``turn_detection.interrupt_response is True``.
- P3.5: ``turn_detection.type == "server_vad"``.
- N3.1: pins the absence of any user-facing override path — there is no
  env var, CLI flag, or settings-UI knob that changes these values.
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

import pytest

from reachy_mini_conversation_app.openai_realtime import OpenaiRealtimeHandler
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def loop():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    try:
        yield new_loop
    finally:
        new_loop.close()


@pytest.fixture
def handler(loop):
    deps = ToolDependencies(reachy_mini=MagicMock(), movement_manager=MagicMock())
    return OpenaiRealtimeHandler(deps)


def _turn_detection(handler) -> dict:
    """Extract the ``turn_detection`` field from the built session config

    in a form that supports both pydantic-style ``model_dump()`` and
    plain TypedDict / dict shapes (OpenAI SDK has shifted between
    representations across versions).
    """
    session_config = handler._get_session_config(tool_specs=[])
    audio = session_config["audio"] if isinstance(session_config, dict) else session_config.audio
    input_cfg = audio["input"] if isinstance(audio, dict) else audio.input
    td = input_cfg["turn_detection"] if isinstance(input_cfg, dict) else input_cfg.turn_detection

    if hasattr(td, "model_dump"):
        return td.model_dump()
    if isinstance(td, dict):
        return dict(td)
    # last resort: dataclass-ish object — read attrs
    return {
        "type": getattr(td, "type"),
        "threshold": getattr(td, "threshold", None),
        "prefix_padding_ms": getattr(td, "prefix_padding_ms", None),
        "silence_duration_ms": getattr(td, "silence_duration_ms", None),
        "interrupt_response": getattr(td, "interrupt_response", None),
    }


# ---------------------------------------------------------------------------
# Positive cases — each tuned VAD field is exactly the value spec'd
# ---------------------------------------------------------------------------


def test_p3_1_threshold_is_0_3(handler):
    """P3.1: VAD threshold lowered from the SDK default 0.5 to 0.3."""
    assert _turn_detection(handler)["threshold"] == pytest.approx(0.3)


def test_p3_2_prefix_padding_ms_is_300(handler):
    """P3.2: explicit prefix padding of 300 ms is sent in the session config."""
    assert _turn_detection(handler)["prefix_padding_ms"] == 300


def test_p3_3_silence_duration_ms_is_500(handler):
    """P3.3: explicit silence-duration of 500 ms is sent in the session config."""
    assert _turn_detection(handler)["silence_duration_ms"] == 500


def test_p3_4_interrupt_response_is_true(handler):
    """P3.4: pre-existing ``interrupt_response=True`` must remain set.

    The pre-fix code passed only ``interrupt_response=True``; the new
    code must not have dropped it while adding the tuned fields.
    """
    assert _turn_detection(handler)["interrupt_response"] is True


def test_p3_5_type_is_server_vad(handler):
    """P3.5: turn-detection mode remains ``server_vad`` (not e.g. semantic_vad)."""
    assert _turn_detection(handler)["type"] == "server_vad"


# ---------------------------------------------------------------------------
# Negative case — VAD values are intentionally not user-tunable today
# ---------------------------------------------------------------------------


VAD_RELATED_ENV_VARS = [
    "OPENAI_VAD_THRESHOLD",
    "OPENAI_VAD_PREFIX_PADDING_MS",
    "OPENAI_VAD_SILENCE_DURATION_MS",
    "VAD_THRESHOLD",
    "VAD_PREFIX_PADDING_MS",
    "VAD_SILENCE_DURATION_MS",
]


def test_n3_1_no_env_var_overrides_vad_values(handler, monkeypatch):
    """N3.1: No environment variable currently overrides the tuned VAD

    values. This test pins the Spec scenario "VAD parameters are not
    exposed as user-tunable today". If a future change introduces such
    a knob, this test will fail and force a parallel spec update.
    """
    for name in VAD_RELATED_ENV_VARS:
        monkeypatch.setenv(name, "0.99")

    td = _turn_detection(handler)
    assert td["threshold"] == pytest.approx(0.3)
    assert td["prefix_padding_ms"] == 300
    assert td["silence_duration_ms"] == 500


def test_n3_1b_session_config_is_deterministic_across_calls(handler):
    """N3.1 (companion): repeated builds of the session config yield the

    same VAD values. Pins that VAD tuning is not derived from any
    mutable runtime state inside the handler.
    """
    first = _turn_detection(handler)
    second = _turn_detection(handler)
    for key in ("type", "threshold", "prefix_padding_ms", "silence_duration_ms", "interrupt_response"):
        assert first[key] == second[key], f"{key!r} changed between session-config builds"
