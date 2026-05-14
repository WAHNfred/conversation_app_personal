"""Regression tests for the media-backend fallback chain in ``main.run()``.

Traceability
------------
- Behavior introduced by commit ``e36cded`` (2026-05-14):
  "fix: media-backend fallback chain + audio frame/VAD robustness".
  Specifically the squashed portions originating from the patches
  ``0005-fix-fallback-to-sounddevice_opencv-when-GStreamer-gi.patch`` and
  ``0006-fix-add-sounddevice_no_video-as-second-media-backend.patch``.
- Specification anchored in commit ``e695e72`` (2026-05-14):
  see ``spec/specs/configuration-and-runtime.md``, Requirement
  "Media Backend Fallback Chain", with the inline traceability tag
  ``(2026-05-14, e36cded)``.
- Hardware context (``CLAUDE.md`` "Hardware target"): the owner runs Reachy
  Mini Wireless where ``gi`` / GStreamer are present. These tests therefore
  exercise behaviour relevant to *other* targets (Reachy Lite, laptops)
  and rely on synthetic ``ImportError`` injection rather than physical
  hardware reproduction.

Coverage matrix
---------------
- P1.1: default backend succeeds, no fallback taken.
- P1.2: ``ImportError("gi")`` → fallback to ``sounddevice_opencv``, succeed.
- P1.3: ``ImportError("gstreamer")`` → fallback to ``sounddevice_opencv``.
- P1.4: default + opencv both fail → fallback to ``sounddevice_no_video``.
- N1.1: ``ImportError`` not mentioning gi/gstreamer → no fallback, exit(1).
- N1.2: all three backends fail → exit(1) with "All media backend fallbacks failed".
- N1.3: generic ``Exception`` (not ImportError) → original handler, no fallback.
- N1.4: opencv raises ``RuntimeError`` (not ImportError) → no_video still tried.
"""

from __future__ import annotations

import argparse
import logging
from unittest.mock import MagicMock

import pytest

from reachy_mini_conversation_app import main as main_mod


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class _AbortRun(BaseException):
    """Marker exception used to halt ``main.run()`` immediately after the

    section under test. ``BaseException`` is intentional: it bypasses the
    ``except Exception`` clauses inside ``run()`` so it always propagates
    out cleanly without triggering the production error path.
    """


def _make_args(**overrides) -> argparse.Namespace:
    """Build the minimal ``argparse.Namespace`` ``main.run()`` accesses

    before our point of interest (the ``ReachyMini(...)`` init block).
    """
    defaults = dict(
        robot_name=None,
        no_camera=False,
        head_tracker=None,
        local_vision=False,
        gradio=False,
        debug=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_robot_that_aborts() -> MagicMock:
    """Return a mock robot whose first downstream call raises ``_AbortRun``.

    ``run()`` immediately calls ``robot.client.get_status()`` after the
    init block; raising there is the cleanest place to halt execution
    before all the camera / movement / gradio setup runs.
    """
    robot = MagicMock()
    robot.client.get_status.side_effect = _AbortRun()
    return robot


# ---------------------------------------------------------------------------
# Why we test via mock call_kwargs and capfd rather than caplog
# ---------------------------------------------------------------------------
#
# ``main.run()`` calls ``utils.setup_logger`` which installs its own stderr
# handler and (importantly) does not propagate to the root logger. Pytest's
# default ``caplog`` fixture hooks into propagation, so warning/error lines
# from ``run()`` never appear in ``caplog.text``. They DO appear on stderr,
# which ``capfd`` captures at the file-descriptor level — so we use that
# fixture for log-text assertions.
#
# The strongest regression signal is actually the *sequence* of
# ``ReachyMini(**kwargs)`` calls (which backends were tried, in which
# order), so most tests rely on ``call_kwargs`` and only spot-check the
# stderr log where it disambiguates an exit path.


# ---------------------------------------------------------------------------
# Positive cases
# ---------------------------------------------------------------------------


def test_p1_1_default_backend_succeeds_no_fallback(monkeypatch, capfd):
    """P1.1: When the default ``ReachyMini(...)`` init succeeds, no fallback

    path runs and no fallback-warning lines are emitted.
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        return _make_robot_that_aborts()

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(_AbortRun):
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert call_kwargs == [{}], "default ReachyMini() should be called exactly once with no media_backend"
    assert "GStreamer backend unavailable" not in err
    assert "sounddevice_opencv" not in err


def test_p1_2_gi_importerror_falls_back_to_opencv(monkeypatch, capfd):
    """P1.2: ``ImportError("No module named 'gi'")`` triggers retry with

    ``media_backend="sounddevice_opencv"``, which succeeds.
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        if "media_backend" not in kwargs:
            raise ImportError("No module named 'gi'")
        return _make_robot_that_aborts()

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(_AbortRun):
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert call_kwargs == [{}, {"media_backend": "sounddevice_opencv"}]
    assert "GStreamer backend unavailable" in err
    assert "Retrying with sounddevice_opencv backend" in err


def test_p1_3_gstreamer_importerror_falls_back_to_opencv(monkeypatch, capfd):
    """P1.3: ImportError with "gstreamer" in the message also triggers fallback."""
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        if "media_backend" not in kwargs:
            raise ImportError("gstreamer plugin failed to load")
        return _make_robot_that_aborts()

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(_AbortRun):
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert call_kwargs == [{}, {"media_backend": "sounddevice_opencv"}]
    assert "GStreamer backend unavailable" in err


def test_p1_4_opencv_fails_falls_back_to_no_video(monkeypatch, capfd):
    """P1.4: Default fails with gi-ImportError, opencv fails with any error,

    then ``sounddevice_no_video`` is tried and succeeds (audio-only start).
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        backend = kwargs.get("media_backend")
        if backend is None:
            raise ImportError("No module named 'gi'")
        if backend == "sounddevice_opencv":
            raise RuntimeError("No camera device available")
        # third call must be no_video — let it succeed
        assert backend == "sounddevice_no_video"
        return _make_robot_that_aborts()

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(_AbortRun):
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert [c.get("media_backend") for c in call_kwargs] == [None, "sounddevice_opencv", "sounddevice_no_video"]
    assert "sounddevice_opencv backend unavailable" in err
    assert "Retrying with sounddevice_no_video backend" in err


# ---------------------------------------------------------------------------
# Negative cases
# ---------------------------------------------------------------------------


def test_n1_1_unrelated_importerror_does_not_trigger_fallback(monkeypatch, capfd):
    """N1.1: ``ImportError`` whose message does NOT mention ``gi`` or

    ``gstreamer`` must NOT trigger the media-backend fallback. It must
    log the generic init-error message and call ``sys.exit(1)``.
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        raise ImportError("No module named 'psutil'")

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert exc_info.value.code == 1
    assert len(call_kwargs) == 1, "no fallback retry should happen for unrelated ImportError"
    assert "Unexpected error during robot initialization" in err
    assert "sounddevice_opencv" not in err


def test_n1_2_all_three_backends_fail_aborts_with_exit_1(monkeypatch, capfd):
    """N1.2: Default + opencv + no_video all fail → final error log and exit(1)."""
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        backend = kwargs.get("media_backend")
        if backend is None:
            raise ImportError("No module named 'gi'")
        if backend == "sounddevice_opencv":
            raise RuntimeError("no camera")
        if backend == "sounddevice_no_video":
            raise RuntimeError("audio device busy")
        pytest.fail(f"Unexpected backend retry: {backend!r}")

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert exc_info.value.code == 1
    assert [c.get("media_backend") for c in call_kwargs] == [None, "sounddevice_opencv", "sounddevice_no_video"]
    assert "All media backend fallbacks failed" in err


def test_n1_3_generic_exception_uses_existing_handler(monkeypatch, capfd):
    """N1.3: Non-ImportError exceptions take the pre-existing generic

    ``except Exception`` path, not the new fallback path. The new
    ImportError handler must not capture them.
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        raise RuntimeError("daemon not running")

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.run(_make_args(), robot=None)

    _, err = capfd.readouterr()
    assert exc_info.value.code == 1
    assert len(call_kwargs) == 1, "no fallback for non-ImportError"
    assert "Unexpected error during robot initialization" in err


def test_n1_4_opencv_runtimeerror_still_continues_to_no_video(monkeypatch):
    """N1.4: The inner ``except (RuntimeError, Exception)`` after the opencv

    retry deliberately catches both error families. This regression test
    pins that behaviour: a ``RuntimeError`` from the opencv attempt
    still triggers the second fallback to ``sounddevice_no_video``.
    """
    call_kwargs = []

    def mock_reachy(**kwargs):
        call_kwargs.append(kwargs)
        backend = kwargs.get("media_backend")
        if backend is None:
            raise ImportError("No module named 'gi'")
        if backend == "sounddevice_opencv":
            raise RuntimeError("opencv install broken")
        return _make_robot_that_aborts()

    monkeypatch.setattr(main_mod, "ReachyMini", mock_reachy)

    with pytest.raises(_AbortRun):
        main_mod.run(_make_args(), robot=None)

    assert [c.get("media_backend") for c in call_kwargs] == [None, "sounddevice_opencv", "sounddevice_no_video"]
