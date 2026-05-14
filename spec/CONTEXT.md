# Reachy Mini Conversation App — Domain Glossary

This is the canonical vocabulary for the Reachy Mini Conversation App. Every Requirement in [`specs/`](specs/), every change proposal, every commit message, and every PR description SHOULD use these terms. When in doubt, prefer the term defined here over a synonym.

This file follows the [Matt Pocock `grill-with-docs`](https://github.com/mattpocock/skills) `CONTEXT.md` format. The skill — and Claude Code in general — uses it to challenge fuzzy language during planning and design sessions.

> **Discovery:** A pointer is left in [`../CLAUDE.md`](../CLAUDE.md) so that any Claude session running in this repo will load the glossary as part of its baseline context.

## Language

### Conversation & Backends

**Conversation**:
One uninterrupted realtime session between the user and the assistant, bounded by stream open and stream close.
_Avoid_: chat, dialogue, session (overloaded — see **Realtime Session**).

**Realtime Backend** (often: **backend**):
One of the three LLM providers that drive the conversation: **Hugging Face**, **OpenAI Realtime**, **Gemini Live**. Selected before stream open and stable for the lifetime of the **Conversation**.
_Avoid_: server, provider, LLM service, model.

**Backend Provider**:
The string identifier of a **Realtime Backend** as written in `BACKEND_PROVIDER`: exactly `huggingface`, `openai`, or `gemini`.
_Avoid_: backend type, vendor.

**Connection Mode**:
For the Hugging Face backend only, one of `deployed` (built-in Space proxy) or `local` (direct websocket via `HF_REALTIME_WS_URL`). Has no meaning for OpenAI or Gemini.
_Avoid_: HF mode, deployment mode.

**Realtime Session** (or: **Session**):
The protocol-level session opened against a **Realtime Backend**, containing the system prompt, the tool specs, the active voice, and the audio stream.
_Avoid_: connection, channel.

**ConversationHandler**:
The abstract base class every backend implementation extends. Owns the public contract: `apply_personality`, transcript emission, shutdown.
_Avoid_: handler (alone — too generic).

**BaseRealtimeHandler**:
The shared scaffolding subclass that OpenAI and Gemini handlers extend. Hugging Face does NOT extend it. Owns session-config construction, tool-spec emission, idle dispatch.
_Avoid_: base handler.

**Voice**:
A backend-specific voice identifier (e.g. `alloy`, `nova`, `shimmer` for OpenAI; different names for Gemini). Resolved through a priority chain — see **Manual Voice Override** vs **Profile Voice**.
_Avoid_: speaker, persona-voice.

**Manual Voice Override**:
A voice the user picked explicitly via the UI. Survives **Hot-Apply** of a different **Profile**.
_Avoid_: custom voice, selected voice.

**Profile Voice**:
The voice declared in `profiles/<name>/voice.txt`. Used only when no **Manual Voice Override** is active.
_Avoid_: default voice (confusing — see resolution chain).

**Transcript**:
One finalized text message attributed to either `user` or `assistant` for exactly one **Turn**. Partial deltas may stream incrementally but coalesce into a single finalized **Transcript** per **Turn**.
_Avoid_: message, log line.

**Turn**:
One half-exchange — either the user speaking once or the assistant responding once. A **Conversation** is a sequence of **Turns**.
_Avoid_: exchange, round.

**Idle Tool Dispatch**:
A **Tool** call the assistant makes spontaneously when the user has been silent past the idle delay. Must not fire while a response is active.
_Avoid_: spontaneous tool, autoplay.

**Idle Tool**:
The `idle_do_nothing` tool specifically — the assistant's explicit choice to stay silent during an idle window. Distinct from **Idle Tool Dispatch**.
_Avoid_: silent tool.

**VAD Commit**:
The backend's signal that the user's voice activity for a single utterance has ended and the audio buffer is closed for transcription.
_Avoid_: utterance end, speech commit.

### Tool System

**Tool**:
A capability exposed to the LLM as an OpenAI-compatible function spec, implemented as a Python subclass of `reachy_mini_conversation_app.tools.core_tools.Tool`. Has a snake_case **Tool Name** and an `async run` method.
_Avoid_: function, capability, command (CLI), action.

**Tool Name**:
The snake_case identifier the LLM uses to call a **Tool** (e.g. `move_head`, `play_emotion`, `dance`). Lives in the **Tool**'s function spec, not in the Python class name.
_Avoid_: function name, command name.

**ToolDependencies**:
The aggregate object passed to every **Tool**'s `run` method. Holds references to `MovementManager`, `CameraWorker`, `BackgroundToolManager`, the vision processor, and other shared singletons.
_Avoid_: tool context, deps.

**Tool Registry**:
The in-process set of registered **Tool** classes, populated once at startup. The **Active Tool Set** is the subset of the registry available to the LLM in the current **Realtime Session**.
_Avoid_: tool list.

**Active Tool Set**:
The **Tools** included in the current **Realtime Session**'s function-spec list, after filtering by both the **Profile Allowlist** and the current **ToolDependencies** availability.
_Avoid_: enabled tools (overloaded — see `tools.txt`).

**Profile Allowlist** (or: **`tools.txt`**):
The newline-separated file inside a **Profile** that names which **Tools** the LLM may call. Comments start with `#`.
_Avoid_: tool config, enabled-tools file.

**Strict Mode**:
The default tool-loading mode. Every name in **`tools.txt`** must resolve to a built-in tool or an **External Tool**; missing names fail startup.
_Avoid_: explicit mode.

**Autoload Mode**:
Activated by `AUTOLOAD_EXTERNAL_TOOLS=1`. Every `*.py` file under `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` is registered, in addition to any explicitly listed.
_Avoid_: convenience mode (used in README but ambiguous), automatic mode.

**Profile-Local Tool**:
A `*.py` file inside the **Profile** folder that defines a custom **Tool**. Resolves before **External Tools** and built-in tools with the same name.
_Avoid_: local tool, profile tool.

**External Tool**:
A `*.py` file under `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` defining a **Tool**. Available to any **Profile** that lists it (or to all profiles in **Autoload Mode**).
_Avoid_: third-party tool, plugin.

**BackgroundToolManager**:
The async orchestrator for **Background Tools**. Owns lifecycle (create / running / completed / cancelled), cleanup, and **ToolNotification** delivery.
_Avoid_: tool manager, task manager.

**Background Tool**:
A **Tool** execution that runs asynchronously and may outlive a **Turn**. The LLM can query its status via `task_status` and cancel it via `task_cancel`.
_Avoid_: async tool, task (alone — ambiguous).

**ToolNotification**:
The payload delivered to the **Realtime Session** when a **Background Tool** completes. Exactly one per completion.
_Avoid_: tool event, completion event.

**ToolProgress**:
A bounded `[0.0, 1.0]` progress value reported by **Background Tools** that opted in via `with_progress=True`.
_Avoid_: progress (alone).

### Motion

**MovementManager**:
The single owner of the robot's pose output, running a dedicated worker thread at 100 Hz. Composes the **Primary Move** with **Secondary Offsets** and writes the result to the SDK.
_Avoid_: motion manager, mover, controller.

**Control Loop**:
The 100 Hz tick inside the **MovementManager** that evaluates the current **Primary Move**, gathers **Secondary Offsets**, blends them, and emits a pose. Frequency is observable via **LoopFrequencyStats**.
_Avoid_: motion loop, tick loop.

**Primary Move**:
A mutually exclusive motion currently driving the robot's pose at time `t`. Comes from a queue. Examples: `BreathingMove`, `DanceQueueMove`, `EmotionQueueMove`, `GotoQueueMove`.
_Avoid_: main move, primary motion.

**Secondary Offset**:
An additive delta applied on top of the **Primary Move**'s pose. Sources: **Speech-Reactive Wobble**, **Head-Tracking Offset**, and listening micro-motions.
_Avoid_: overlay, modifier.

**Move**:
The protocol every queueable motion implements — exposes `evaluate(t) -> FullBodyPose`. Wrapper classes adapt dance / emotion / goto objects to this protocol.
_Avoid_: animation, behaviour.

**BreathingMove**:
The default idle **Primary Move**. Starts automatically after the **Idle Delay** when the queue is empty. Interpolates smoothly from the last held pose into a continuous breathing pattern.
_Avoid_: idle animation, default move.

**DanceQueueMove / EmotionQueueMove / GotoQueueMove**:
Adapters that wrap a dance, an emotion clip, or a goto target so they satisfy the **Move** protocol.
_Avoid_: dance, emotion, goto (alone — those are the wrapped objects).

**Idle Delay**:
The duration of inactivity after which `MovementManager` auto-starts a **BreathingMove**.
_Avoid_: idle timer, breathing delay.

**Speech-Reactive Wobble** (implementation: **HeadWobbler**):
A **Secondary Offset** derived from the assistant's audio amplitude. Produces a subtle head sway while the assistant speaks.
_Avoid_: speech wobble (acceptable shorthand), audio motion.

**Head-Tracking Offset**:
A **Secondary Offset** derived from the **Head Tracker** subprocess output. Applied only when the `head_tracking` **Tool** has been toggled on by the LLM.
_Avoid_: face offset, tracking offset.

**Listening Mode** (or: **Listening Hold**):
The motion subsystem's state while the user is speaking — secondary speech offsets are clamped to a steady listening pose so the robot visibly attends. Released only when the user stops speaking, never by a tool completion.
_Avoid_: paused, frozen.

### Perception

**CameraWorker**:
The thread that captures camera frames into a single-slot frame buffer and optionally feeds a **Head Tracker**. Disabled by `--no-camera`.
_Avoid_: capture loop, camera thread.

**Frame Buffer**:
The single-slot, thread-safe buffer the **CameraWorker** writes to. Consumers always read the most recent frame; older unread frames are discarded.
_Avoid_: frame queue (misleading — depth 1).

**Head Tracker**:
A backend that detects head position in a frame. Selectable at startup via `--head-tracker {yolo, mediapipe}`. YOLO runs out-of-process; MediaPipe runs in-process via `reachy_mini_toolbox`.
_Avoid_: face tracker (it tracks head position, not identity).

**Head Tracking** (capability):
The combination of **Head Tracker** producing offsets and the `head_tracking` **Tool** toggling whether those offsets blend into the pose. Distinguished from **Identity Recognition**, which does NOT happen.
_Avoid_: face recognition, person tracking.

**Backend Vision Mode**:
The default mode of the `camera` **Tool**. Encodes the latest frame as JPEG and forwards it to the **Realtime Backend** for analysis.
_Avoid_: remote vision.

**Local Vision Mode**:
Activated by `--local-vision`. The `camera` **Tool** runs inference on the local **VisionProcessor** instead of forwarding to the backend. Returns text directly to the LLM as the tool result.
_Avoid_: on-device vision (acceptable), offline vision.

**VisionProcessor**:
The on-device VLM wrapper around SmolVLM2. Selects an inference device (MPS / CUDA / CPU) and runs `process_image(bgr_frame, prompt)`.
_Avoid_: vision model, VLM wrapper.

### Personality

**Profile**:
A named folder under `profiles/<name>/` (or under the **External Profiles Directory**) containing at minimum `instructions.txt`. May also contain `tools.txt`, `voice.txt`, and **Profile-Local Tools**.
_Avoid_: personality (alone — see below), character.

**Personality**:
The user-facing concept rendered in the UI's "Personality" accordion. Backed by a **Profile**. The terms are used interchangeably in user docs; in the spec, prefer **Profile**.
_Avoid_: persona (we don't use this term).

**Active Profile**:
The **Profile** currently driving the **Realtime Session**'s system prompt. Resolved by the **Profile Resolution Chain**; changeable at runtime via **Hot-Apply** unless **Locked Profile Mode** is on.
_Avoid_: current profile.

**Hot-Apply**:
The action of sending a new **Profile**'s composed instructions to the live **Realtime Session** without dropping the WebRTC stream. Triggered by the Apply button in the Gradio UI.
_Avoid_: live reload, switch.

**Locked Profile Mode**:
The compile-time lock activated by setting `LOCKED_PROFILE` to a profile name in `config.py`. The app uses that profile and ignores saved startup settings, `REACHY_MINI_CUSTOM_PROFILE`, and any UI selection. The UI shows "(locked)" and disables profile editing.
_Avoid_: pinned profile.

**External Profile**:
A **Profile** under `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` rather than the packaged `profiles/` root. Subject to the same loading rules but falls back to the default `tools.txt` if it has none.
_Avoid_: custom profile (overloaded — `REACHY_MINI_CUSTOM_PROFILE` selects ANY profile, internal or external).

**Prompt Placeholder**:
A token of the form `[name]` or `[nested/name]` inside `instructions.txt` that gets replaced with the content of the matching file under `src/reachy_mini_conversation_app/prompts/`.
_Avoid_: macro, snippet, include.

**Profile Resolution Chain**:
The startup priority order: (1) **Locked Profile Mode**, (2) saved **Startup Settings**, (3) `REACHY_MINI_CUSTOM_PROFILE` env var, (4) the `default` **Profile**.
_Avoid_: profile lookup, profile selection.

**Startup Settings** (file: `startup_settings.json`):
Instance-local persisted state — the **Profile** and **Voice** the user saved as their session default. Ignored under **Locked Profile Mode**.
_Avoid_: user preferences, settings (alone — too generic).

### Configuration & Runtime

**Instance `.env`**:
The `.env` file at the working-directory root, owned by the running instance and written by the **Persistence Helpers**. Distinct from `.env.example` (the repo-shipped template) and from process environment variables.
_Avoid_: env file (without qualifier), config file.

**Persistence Helper**:
A function in `config.py` that writes a value to both the **Instance `.env`** and the in-memory process environment in one step, so subsequent reads observe the change without restart.
_Avoid_: env writer, setter.

**Runtime Refresh**:
Calling `refresh_runtime_config_from_env()` to re-derive the mutable config object from current environment after a **Persistence Helper** mutation.
_Avoid_: reload, refresh (alone).

**Name Collision Protection**:
The startup check (`_raise_on_name_collisions`) that refuses to start when an external tool / profile shares a name with a built-in counterpart.
_Avoid_: name check.

**Source Checkout**:
A working tree where the package is run from the repo (not from an installed wheel). Detected by `_is_source_checkout_root`. Changes `profiles/` discovery to use the on-disk folder rather than `reachy_talk_data` packaged data.
_Avoid_: dev mode, editable install.

### User Interfaces

**Console Mode**:
The default UI surface — terminal output plus the robot's microphone/speaker via **LocalStream**. Active when `--gradio` is NOT given.
_Avoid_: CLI mode, headless mode (overloaded — see below).

**Gradio Mode**:
The Web UI surface activated by `--gradio`. Serves a browser app at `http://127.0.0.1:7860/` with the conversation, the **Personality Accordion**, and the **Settings Panel**.
_Avoid_: web mode, browser UI.

**LocalStream**:
The bidirectional audio bridge between the robot's recorder/player and the **Realtime Backend** when in **Console Mode**. WebRTC handles the same role under **Gradio Mode**.
_Avoid_: audio stream.

**Headless Settings UI**:
FastAPI routes mounted in both **Console Mode** and **Gradio Mode** that expose backend/credential/voice configuration in a browser. "Headless" here means "no Gradio frontend wrapping it" — it still has a UI.
_Avoid_: headless mode (would imply no UI at all).

**Personality Accordion**:
The collapsible Gradio section that lets the user select a **Profile**, apply it via **Hot-Apply**, save it as the **Startup Settings**, or create a new **Profile**.
_Avoid_: personality panel, profile picker (acceptable shorthand).

**Settings Panel**:
The UI section for **Backend Provider** selection, credentials, and **Connection Mode**. Backed by the **Headless Settings UI** routes.
_Avoid_: config panel, options.

**Simulation Mode**:
A mode where the robot is simulated rather than physically connected. Requires **Gradio Mode**.
_Avoid_: virtual mode, fake mode.

## Relationships

### Conversation pipeline
- A **Conversation** opens exactly one **Realtime Session** with exactly one **Realtime Backend**.
- A **Realtime Session** carries one **Active Tool Set** and one active **Voice**.
- A **Conversation** is a sequence of **Turns**; each **Turn** emits exactly one finalized **Transcript**.
- An **Idle Tool Dispatch** may occur only when no **Turn** is in progress.

### Profile binding
- An **Active Profile** populates the system prompt of the open **Realtime Session**.
- The **Profile Resolution Chain** picks the **Active Profile** at startup.
- **Hot-Apply** replaces the **Active Profile** in-place; it does NOT change the **Active Tool Set** (tools are loaded once at startup).
- **Locked Profile Mode** disables **Hot-Apply** and forces the **Active Profile** to a single value.

### Motion composition
- The **MovementManager** runs the **Control Loop** at 100 Hz.
- At each tick the pose = **Primary Move** at `t` combined with the sum of **Secondary Offsets**.
- Only one **Primary Move** runs at a time; new moves queue behind it.
- The **Speech-Reactive Wobble** and the **Head-Tracking Offset** are independent **Secondary Offsets** that compose additively.
- **Listening Mode** clamps the **Speech-Reactive Wobble** to a steady hold.

### Tool dispatch
- The LLM emits a function call → dispatcher looks up the **Tool Name** in the **Active Tool Set** → invokes the **Tool**'s `async run` with **ToolDependencies**.
- A **Background Tool** is registered with the **BackgroundToolManager**, which emits exactly one **ToolNotification** on completion.
- The `task_status` and `task_cancel` tools introspect the **BackgroundToolManager**.

### Perception flow
- The **CameraWorker** writes to a single-slot **Frame Buffer**.
- The selected **Head Tracker** reads frames and produces a position; the `head_tracking` **Tool** toggles whether that position becomes a **Head-Tracking Offset**.
- The `camera` **Tool** in **Backend Vision Mode** forwards the latest frame to the **Realtime Backend**; in **Local Vision Mode** it runs inference via the **VisionProcessor**.

## Example dialogue

> **Contributor:** "I want to add a tool that lets the assistant pause the current animation for 5 seconds."
> **Domain expert:** "Pause what exactly — the **Primary Move** or all motion? Those are different things. **Secondary Offsets** like the **Speech-Reactive Wobble** and **Head-Tracking Offset** are independent of the **Primary Move**."
>
> **Contributor:** "I meant the dance that's playing."
> **Domain expert:** "Then you mean pause the current **Primary Move** — specifically the `DanceQueueMove`. We already have `stop_dance` which clears it. What does 'pause' add — resume capability? Because `stop_dance` is destructive and there's no per-move resume today."
>
> **Contributor:** "Yes, resume after 5 seconds."
> **Domain expert:** "That's a new concept — the **Move** protocol exposes `evaluate(t)` and assumes monotonically increasing `t`. A resumable pause needs the **MovementManager** to retain the move and offset its `t`. That's an addition to [`motion-system`](specs/motion-system.md) — propose a new Requirement there before writing code."
>
> **Contributor:** "Could the tool just call `stop_dance`, sleep, and call `dance` again?"
> **Domain expert:** "No — `dance` queues a fresh **Primary Move** from index zero. Re-queuing is not pause-resume. Either we keep it simple and call it `stop_dance_with_resume_intent` (which we don't actually want to add — see the spec's discussion of tool naming), or we add a real pause primitive to **MovementManager**. The first is sugar; the second is a real capability. Pick one explicitly."

## Flagged ambiguities

- **"Backend"** was sometimes used to mean (a) the **Realtime Backend** provider, (b) the Hugging Face *server* the deployed connection mode talks to, (c) the FastAPI app under Gradio. **Resolution:** "Backend" alone means **Realtime Backend** in this codebase. The HF server is "the Hugging Face Space" or "the local speech-to-speech server"; the FastAPI surface is "the FastAPI app" or "the **Headless Settings UI**".

- **"Vision"** is ambiguous between **Backend Vision Mode** and **Local Vision Mode**. **Resolution:** always qualify. The CLI flag `--local-vision` toggles between them; defaults are backend-driven.

- **"Voice"** flows through a 3-step priority: **Manual Voice Override** > **Profile Voice** > backend default. **Resolution:** use the named term for whichever layer of the chain you're discussing.

- **"Tool"** can mean (a) a **Tool** subclass exposed to the LLM, (b) the `pip` package's CLI executable, (c) `ruff` / `mypy` / `pytest` toolchain. **Resolution:** "Tool" with an initial capital, or qualified ("LLM tool"), always means the **Tool** subclass. Toolchain is "linters" / "type checker" / "test runner".

- **"Personality" vs "Profile"** — README and the UI call it "Personality"; the codebase uses "profile". **Resolution:** in spec / planning text use **Profile**; in user-facing copy use **Personality**.

- **"Headless"** is used for two unrelated things: (a) running without Gradio (console mode → see **Console Mode**), (b) the FastAPI settings routes (called **Headless Settings UI** because there is no Gradio shell around them). **Resolution:** never use "headless mode" alone; say "Console Mode" or "Headless Settings UI" explicitly.

- **"Locked"** vs "**Custom**" vs "**External**" profile selection mechanisms are three independent things: **Locked Profile Mode** is a compile-time lock; `REACHY_MINI_CUSTOM_PROFILE` is a runtime env fallback for ANY profile (built-in or external); **External Profile** describes where the **Profile** files live on disk. **Resolution:** these are orthogonal — name the specific mechanism, never collapse them.

- **"Idle"** appears in two places: the **Idle Delay** that triggers **BreathingMove**, and the **Idle Tool Dispatch** that fires when the user has been silent. **Resolution:** always say which.

- **"Stop"** vs "**Cancel**" — `stop_dance` and `stop_emotion` clear queued moves; `task_cancel` cancels a **Background Tool**. **Resolution:** "stop" applies to **Primary Moves**; "cancel" applies to **Background Tools**.
