# Project Context

## Purpose

The **Reachy Mini Conversation App** is a real-time, voice-first conversational application for the [Reachy Mini](https://github.com/pollen-robotics/reachy_mini/) humanoid tabletop robot. It connects three concerns that historically required separate codebases:

1. **Low-latency speech-to-speech dialogue** with a large-language-model backend (Hugging Face, OpenAI Realtime, or Gemini Live).
2. **Robotic embodiment** — coordinated head motion, antennae behaviors, dances, recorded emotion clips, and breathing — synchronized with what the assistant is saying and what it sees.
3. **Personality and tool customization** — swappable profiles that change prompt, voice, available tools, and custom motion primitives without touching the codebase.

The app is the canonical reference implementation for "talking to a Reachy Mini." It ships as the bundled experience on Hugging Face Spaces, on the Reachy Mini Wireless image, and as a `pip` / `uv` installable Python package for laptop-based experimentation.

## Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.12 | SDK requirement; type-hinted code with `mypy` strict-ish settings |
| Realtime transport | [`fastrtc`](https://github.com/freddyaboulton/fastrtc) + `aiortc` | WebRTC audio/video at low latency, browser-compatible |
| LLM backends | OpenAI Realtime SDK (`openai`), Google `google-genai`, Hugging Face OpenAI-compatible WebSocket | Each backend speaks roughly the same realtime protocol, abstracted by `BaseRealtimeHandler` |
| Web UI | [`gradio`](https://www.gradio.app/) 5.x | Built-in WebRTC bridge, mounts settings + chat in one app |
| Robot SDK | `reachy-mini`, `reachy_mini_toolbox`, `reachy_mini_dances_library` | Hardware abstraction, kinematics, and content libraries published by Pollen Robotics |
| Vision | Optional — `transformers` (SmolVLM2), `ultralytics` (YOLO), `mediapipe` | Pulled in as `pip` extras (`local_vision`, `yolo_vision`, `mediapipe_vision`) |
| Packaging | `setuptools` + custom `BuildPyWithProfiles` | Copies `profiles/` into the wheel as `reachy_talk_data` so installed copies retain personalities |
| Test / lint / type | `pytest`, `pytest-asyncio`, `ruff`, `mypy` | CI gates every PR |

## Architecture Overview

The app is layered. Each layer has a single owner and a narrow interface:

```
┌─────────────────────────────────────────────────────────────────┐
│  User (audio + video in/out)                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │ WebRTC (fastrtc)
┌────────────────────▼────────────────────────────────────────────┐
│  UI Layer                                                       │
│  ├─ Console mode (default)                                      │
│  └─ Gradio Web UI (--gradio)                                    │
│     ├─ Conversation surface (chatbot + audio + webcam)          │
│     └─ Settings / Personality accordion                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  ConversationHandler (ABC)                                      │
│  ├─ OpenAIRealtimeHandler                                       │
│  ├─ GeminiLiveHandler                                           │
│  └─ HuggingFaceRealtimeHandler                                  │
│      ↓ shares                                                   │
│  BaseRealtimeHandler (OpenAI-shaped: session, tools, audio,     │
│                       transcripts, function calls)              │
└────────────────────┬────────────────────────────────────────────┘
                     │ tool calls
┌────────────────────▼────────────────────────────────────────────┐
│  Tool System                                                    │
│  ├─ Tool registry (subclasses of core_tools.Tool)               │
│  ├─ BackgroundToolManager (async dispatch, cancel, status)      │
│  └─ ToolDependencies (movement, camera, vision, tracking)       │
└────────────────────┬────────────────────────────────────────────┘
                     │ commands
┌────────────────────▼────────────────────────────────────────────┐
│  Motion + Perception                                            │
│  ├─ MovementManager (100 Hz control loop)                       │
│  │   ├─ Primary moves: dances, emotions, goto, breathing        │
│  │   └─ Secondary moves: speech-reactive wobble, head offsets   │
│  ├─ CameraWorker (frame buffer, optional head tracker)          │
│  └─ Vision processor (SmolVLM2 local OR backend vision)         │
└────────────────────┬────────────────────────────────────────────┘
                     │ reachy_mini SDK
┌────────────────────▼────────────────────────────────────────────┐
│  Physical Robot                                                 │
└─────────────────────────────────────────────────────────────────┘
```

The three god-nodes that connect this graph (per the knowledge-graph analysis) are:

- **`ToolDependencies`** (degree 70) — passed to every tool; the seam between Conversation, Motion, and Perception.
- **`BaseRealtimeHandler`** (degree 41) — shared protocol scaffolding for OpenAI and Gemini handlers.
- **`MovementManager`** (degree 32) — single owner of the 100 Hz control loop and queue arbitration.

## Personas

The app is consumed by three distinct audiences. The spec must serve all three:

- **End user** — owns a Reachy Mini, wants to talk to it. Cares about install, profile selection, and that conversation just works.
- **Profile author** — wants to author a personality (a children's book character, a chess coach, a Mars rover) without writing Python. Cares about `instructions.txt`, `tools.txt`, prompt placeholders, and the few customization escape hatches.
- **Contributor / cloner** — wants to extend the app: add a backend, add a tool, lock the profile for a dedicated clone. Cares about extension points, locked-profile mode, and external-content directories.

## Project Conventions

### Code organization

- Source under `src/reachy_mini_conversation_app/`.
- Tools under `src/reachy_mini_conversation_app/tools/`. Each tool is a subclass of `Tool` with a `function_spec` classmethod and an `async run` method.
- Realtime handlers at package root (`openai_realtime.py`, `gemini_live.py`, `huggingface_realtime.py`, `base_realtime.py`, `conversation_handler.py`).
- Profiles under `profiles/<name>/` with at minimum `instructions.txt`. Optional `tools.txt`, `voice.txt`, and `*.py` custom tool files.
- Prompts under `src/reachy_mini_conversation_app/prompts/` (referenced from `instructions.txt` via `[name]` or `[nested/name]` placeholders).
- Tests mirror source layout under `tests/`. Vision and tool subdirectories live under `tests/vision/` and `tests/tools/`.

### Naming

- Tool class names are `PascalCase`, exposed to the LLM under their `function_spec`-declared `name` (snake_case).
- Realtime handler classes end in `Handler`. Concrete handlers always extend either `ConversationHandler` directly (Hugging Face) or `BaseRealtimeHandler` (OpenAI, Gemini).
- Profile folder names are snake_case and must not collide with built-in tool module names — `config._raise_on_name_collisions` enforces this at startup.
- Movement classes implement the `Move` protocol (`evaluate(t) -> FullBodyPose`).

### Quality bar

- Every bug fix lands with a regression test.
- New features land with at least one happy-path test.
- `ruff check`, `ruff format`, `mypy`, `pytest` all run in CI.
- AI-generated code is reviewed by a human, kept minimal, and not bulk-applied. See `CONTRIBUTING.md`.

### Distribution

- The package is built with `setuptools` plus a custom `BuildPyWithProfiles` step that copies `profiles/` into `reachy_talk_data` inside the wheel. Profiles ship with the install — they are not external assets at runtime.
- Released by tagging `vX.Y.Z`. A separate Hugging Face Spaces mirror is synced on `main` so the demo Space and the package stay in lockstep.

## Out of Scope (for this spec)

These are deliberately *not* described as requirements because they are either upstream concerns or implementation details that can change without breaking the user contract:

- The wire format of any specific realtime backend (OpenAI, Gemini, Hugging Face) — those are owned by their respective providers.
- The internal animation curves of individual dances or emotions — those live in the `reachy-mini-dances-library` and `reachy-mini-emotions-library` Hugging Face datasets and have their own versioning.
- The `reachy-mini` SDK's kinematic chain — the conversation app uses the SDK and trusts it.
- CI workflow internals (`.github/workflows/`) — described separately in `CONTRIBUTING.md`.
