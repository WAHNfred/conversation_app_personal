# Spec: Realtime Conversation & Backends

## Purpose

Defines the realtime voice conversation loop and the three pluggable backend providers. This capability owns:

- The `ConversationHandler` ABC and `BaseRealtimeHandler` shared scaffolding.
- The three concrete backends: OpenAI Realtime, Gemini Live, Hugging Face Realtime.
- Selection logic that maps user configuration (env vars, settings UI) to a concrete handler.
- Session lifecycle: connect, tool wiring, voice change, transcript emission, graceful shutdown.

It does **not** own: tool execution (see [tool-system](tool-system.md)), motion (see [motion-system](motion-system.md)), or UI surfaces (see [user-interfaces](user-interfaces.md)).

## Requirements

### Requirement: Pluggable Realtime Backends

The system SHALL support three swappable realtime backend providers selected at runtime: `huggingface` (default), `openai`, and `gemini`. Selection MUST occur before the audio stream opens and MUST be deterministic given the resolved configuration.

#### Scenario: Default selection without configuration

- **GIVEN** a fresh install with no `.env`, no environment variables, and no persisted startup settings
- **WHEN** the app starts
- **THEN** the configured backend is `huggingface` and the connection mode is `deployed` (built-in Hugging Face Space proxy)
- **AND** no API key is required to start a conversation

#### Scenario: Explicit OpenAI selection via env

- **GIVEN** an `.env` containing `BACKEND_PROVIDER=openai` and a valid `OPENAI_API_KEY`
- **WHEN** the app starts
- **THEN** an `OpenAIRealtimeHandler` is instantiated targeting model `gpt-realtime-2` (or the override in `MODEL_NAME`)
- **AND** the active voice list comes from the OpenAI voice catalogue

#### Scenario: Explicit Gemini selection via env

- **GIVEN** an `.env` containing `BACKEND_PROVIDER=gemini` and a valid `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
- **WHEN** the app starts
- **THEN** a `GeminiLiveHandler` is instantiated targeting model `gemini-3.1-flash-live-preview` (or the override in `MODEL_NAME`)
- **AND** profile voices are mapped to the nearest equivalent Gemini voice

#### Scenario: Unknown backend value fails fast

- **GIVEN** `BACKEND_PROVIDER=foobar` in `.env`
- **WHEN** the app reads its configuration
- **THEN** startup fails with an explicit error naming the invalid provider
- **AND** the app does NOT silently fall through to the default Hugging Face backend

### Requirement: Backend Inference From Model Name

When `BACKEND_PROVIDER` is unset but `MODEL_NAME` is set, the system SHALL infer the backend from the model name only when the model unambiguously belongs to one provider; otherwise it SHALL default to `huggingface`.

#### Scenario: Gemini model name infers Gemini backend

- **GIVEN** `MODEL_NAME=gemini-3.1-flash-live-preview` and `BACKEND_PROVIDER` is unset
- **WHEN** the app reads its configuration
- **THEN** `is_gemini_model()` returns true
- **AND** the resolved backend is `gemini`

#### Scenario: Non-Gemini model name defaults to Hugging Face

- **GIVEN** `MODEL_NAME=some-other-model` and `BACKEND_PROVIDER` is unset
- **WHEN** the app reads its configuration
- **THEN** the resolved backend is `huggingface`

### Requirement: Hugging Face Connection Modes

The Hugging Face backend SHALL support two connection modes selectable via `HF_REALTIME_CONNECTION_MODE`: `deployed` (built-in Space proxy) and `local` (direct websocket to a user-provided endpoint).

#### Scenario: Deployed mode uses built-in Space proxy

- **GIVEN** `BACKEND_PROVIDER=huggingface` and `HF_REALTIME_CONNECTION_MODE=deployed`
- **WHEN** the realtime handler connects
- **THEN** the websocket target is the built-in Hugging Face Space proxy URL (`get_hf_session_url()`)
- **AND** `HF_REALTIME_WS_URL` is ignored

#### Scenario: Local mode requires a websocket URL

- **GIVEN** `BACKEND_PROVIDER=huggingface` and `HF_REALTIME_CONNECTION_MODE=local`
- **WHEN** `HF_REALTIME_WS_URL` is empty
- **THEN** the configuration is rejected and the UI surfaces the missing-URL error
- **AND** no websocket connection is attempted

#### Scenario: Local mode accepts base URL or full realtime path

- **GIVEN** `HF_REALTIME_CONNECTION_MODE=local`
- **WHEN** `HF_REALTIME_WS_URL` is either `ws://127.0.0.1:8765/v1` or `ws://127.0.0.1:8765/v1/realtime`
- **THEN** `parse_hf_direct_target` normalizes both inputs to the same realtime endpoint

#### Scenario: Connection mode is never inferred from URL

- **GIVEN** an explicit `HF_REALTIME_WS_URL` value is set
- **WHEN** `HF_REALTIME_CONNECTION_MODE` is not also set
- **THEN** the app does NOT infer `local` mode from the URL's presence
- **AND** the configuration is rejected with a message identifying the missing mode

### Requirement: Shared Session Scaffolding

The OpenAI and Gemini handlers SHALL extend `BaseRealtimeHandler` to share session-config construction, tool-spec emission, transcript bookkeeping, idle-tool dispatch, and shutdown. The Hugging Face handler MAY extend `ConversationHandler` directly when its wire protocol diverges from OpenAI's session shape.

#### Scenario: Both providers consume the same tool specs

- **GIVEN** an active profile with tools `move_head`, `dance`, `camera`, `head_tracking`
- **WHEN** an `OpenAIRealtimeHandler` and a `GeminiLiveHandler` are each started against that profile
- **THEN** both handlers receive identical tool specs from `get_active_tool_specs()`
- **AND** Gemini's `_convert_schema_types` translates the OpenAI-shaped specs to Gemini's schema dialect before sending

#### Scenario: Tool spec is filtered when dependency is unavailable

- **GIVEN** the camera worker is disabled (`--no-camera`)
- **WHEN** the session config is built
- **THEN** the `camera` and `head_tracking` tool specs are excluded
- **AND** the LLM cannot call those tools

### Requirement: Session Instructions and Personality Composition

When a session opens or a personality is applied at runtime, the handler SHALL load instructions composed by [personality-system](personality-system.md) and send them as the session's system prompt.

#### Scenario: Initial session instructions come from active profile

- **GIVEN** the active profile is `mars_rover`
- **WHEN** the realtime session opens
- **THEN** the session instructions are the composed content of `profiles/mars_rover/instructions.txt` with all `[placeholder]` references resolved
- **AND** the placeholders pull from `src/reachy_mini_conversation_app/prompts/`

#### Scenario: Hot personality switch updates live session

- **GIVEN** a running session under profile `default`
- **WHEN** the user clicks Apply on personality `chess_coach` in the Gradio UI
- **THEN** `apply_personality` is called on the active handler
- **AND** the new instructions are sent to the live session without dropping the WebRTC connection
- **AND** the tool set remains unchanged (tools are loaded at startup only)

### Requirement: Voice Selection Per Backend

Each backend SHALL expose a backend-specific set of voices, and the active voice MUST be either the user-selected one (persisted in startup settings) or the profile's `voice.txt` value, falling back to the backend's default.

#### Scenario: Manual voice override survives profile change

- **GIVEN** the user has manually selected voice `nova` for the Gemini backend
- **WHEN** the user applies a different profile that specifies a different voice in `voice.txt`
- **THEN** the manually selected `nova` remains active

#### Scenario: Persisted startup voice is restored on relaunch

- **GIVEN** the user previously saved `shimmer` as their startup voice on the OpenAI backend
- **WHEN** the app launches and the OpenAI handler initializes
- **THEN** the startup voice `shimmer` is sent in the initial session config

#### Scenario: Profile voice applies when no manual override exists

- **GIVEN** no manual voice override is persisted
- **AND** the active profile has `voice.txt` containing `alloy`
- **WHEN** the session opens
- **THEN** the session uses `alloy`

### Requirement: Transcript Emission

Both user and assistant turns SHALL emit exactly one finalized transcript message per turn to the UI. Partial deltas MAY be emitted incrementally but MUST coalesce into a single final message.

#### Scenario: Gemini emits one user and one assistant transcript per turn

- **GIVEN** a Gemini Live session
- **WHEN** the user speaks one utterance and Gemini responds
- **THEN** the UI receives one transcript with role `user` and one with role `assistant`
- **AND** intermediate `flush_transcript_chunks` deltas do not produce duplicate finalized messages

#### Scenario: Hugging Face partial transcript snapshots accumulate per item

- **GIVEN** a Hugging Face Realtime session
- **WHEN** the backend emits partial transcript deltas for a single `item_id`
- **THEN** `InputTranscriptChunksByItem` keeps only the current item's deltas
- **AND** a new `item_id` clears the accumulator before recording

### Requirement: Idle-Tool Dispatch and Speech Suppression

While a response is active, the handler SHALL NOT trigger idle tools. Idle tools MAY fire only after a response is fully complete and the user has not begun a new turn.

#### Scenario: Idle tool does not fire mid-response

- **GIVEN** the assistant is mid-speech
- **WHEN** the idle delay elapses
- **THEN** no idle tool dispatch occurs

#### Scenario: User speech postpones idle behavior

- **GIVEN** the assistant has just finished speaking
- **WHEN** the user begins speaking before the idle delay elapses
- **THEN** the idle timer resets and no idle tool fires

#### Scenario: Tool completion does not interrupt ongoing speech wobble

- **GIVEN** the assistant is speaking and the speech-reactive head wobbler is active
- **WHEN** a background tool completes and emits a `ToolNotification`
- **THEN** the wobbler continues against the audio stream
- **AND** the assistant's audio is not interrupted

### Requirement: Empty / Blank VAD Commits Are Recoverable

When the realtime backend reports an empty user audio buffer or an empty user transcript, the handler SHALL exit listening state and restore post-speech motion without surfacing a chat-level error.

#### Scenario: Empty audio buffer error exits listening state cleanly

- **GIVEN** the OpenAI backend sends an `input_audio_buffer.commit` followed by an empty-buffer error
- **WHEN** the handler processes the error
- **THEN** listening mode is exited
- **AND** no error message is added to the chat transcript

#### Scenario: Blank VAD commit unfreezes listening motion

- **GIVEN** the realtime backend commits a blank VAD utterance
- **WHEN** the handler observes the empty transcript
- **THEN** the listening-frozen secondary motion is released and the robot resumes neutral motion

### Requirement: Audio Frame Normalization To 1-D Mono _(2026-05-14, `e36cded`)_

`BaseRealtimeHandler.receive()` SHALL accept an input audio frame of any common shape produced by `aiortc` (1-D, channels-first 2-D `(C, N)`, or channels-last 2-D `(N, C)`) and SHALL always collapse it to a 1-D mono array before resampling. The first channel MUST be retained; additional channels SHALL be discarded.

The pre-fix code transposed `(1, 960)` to `(960, 1)` but never squeezed the singleton channel dimension, leaving downstream resample/buffer logic operating on a 2-D array. This requirement closes that gap.

#### Scenario: Channels-first frame `(1, N)` is collapsed correctly

- **GIVEN** a frame with shape `(1, 960)` from `aiortc`
- **WHEN** `receive()` processes the frame
- **THEN** it is transposed to `(960, 1)` and then collapsed to a 1-D array of length 960
- **AND** downstream resampling operates on the 1-D array

#### Scenario: Multi-channel frame keeps only the first channel

- **GIVEN** a 2-D frame with two or more channels (e.g. shape `(960, 2)`)
- **WHEN** `receive()` processes the frame
- **THEN** the first channel is retained as a 1-D array of the same length
- **AND** the additional channels are discarded

#### Scenario: Already-1-D frame passes through unchanged

- **GIVEN** an input frame that is already a 1-D array
- **WHEN** `receive()` processes the frame
- **THEN** no reshape or transpose is performed
- **AND** the array is forwarded to the resampler unchanged

### Requirement: Silent-Microphone Diagnostic Warning _(2026-05-14, `e36cded`)_

On the **first** audio frame received in a session, the handler SHALL inspect the frame's peak amplitude and emit exactly one diagnostic log line:

- A `warning` line if the peak amplitude is exactly zero (microphone is delivering silence — typically a missing browser/OS permission).
- An `info` line confirming the non-zero peak otherwise.

This check SHALL run at most once per handler instance — subsequent frames MUST NOT re-trigger it, regardless of their content.

#### Scenario: All-zero first frame warns operator

- **GIVEN** a freshly opened realtime session
- **WHEN** the first audio frame is received with `peak == 0`
- **THEN** exactly one warning line is logged identifying the silent-mic condition and pointing at microphone permissions
- **AND** the silence check is marked done so it does not fire on subsequent frames

#### Scenario: Non-zero first frame logs confirmation

- **GIVEN** a freshly opened realtime session
- **WHEN** the first audio frame is received with a non-zero peak amplitude
- **THEN** exactly one info line is logged stating the peak value as non-silent
- **AND** the silence check is marked done

#### Scenario: Subsequent silent frames do NOT re-warn

- **GIVEN** the silence check has already run for this handler instance
- **WHEN** later frames arrive (including ones with `peak == 0`)
- **THEN** no additional silence-related log lines are emitted

### Requirement: OpenAI Server-VAD Tuning _(2026-05-14, `e36cded`)_

`OpenaiRealtimeHandler` SHALL configure the OpenAI realtime session's server-side voice-activity detector with non-default parameters tuned for laptop/desktop microphones rather than the SDK defaults. Specifically: `threshold=0.3`, `prefix_padding_ms=300`, `silence_duration_ms=500`, `interrupt_response=true`.

The pre-fix configuration used only `interrupt_response=true` and accepted the SDK defaults (notably the more conservative `threshold=0.5`), which was unresponsive on consumer laptop microphones.

#### Scenario: Session config carries the tuned VAD parameters

- **GIVEN** an `OpenaiRealtimeHandler` is starting a session
- **WHEN** the session config is built
- **THEN** the input `turn_detection` is a `ServerVad` with `threshold=0.3`, `prefix_padding_ms=300`, `silence_duration_ms=500`, `interrupt_response=true`
- **AND** these values are sent verbatim to OpenAI Realtime

#### Scenario: VAD parameters are not exposed as user-tunable today

- **GIVEN** a user wants to adjust VAD sensitivity
- **WHEN** they look for a config knob in `.env`, the CLI, or the settings UI
- **THEN** no such knob exists in the current implementation
- **AND** changes require editing `openai_realtime.py` directly

### Requirement: Response Timeout Guard

If the realtime backend never sends `response.done` after a response begins, the sender loop SHALL time out cleanly rather than block indefinitely.

#### Scenario: Missing response.done times out

- **GIVEN** a response was started but `response.done` is never received
- **WHEN** the sender loop waits longer than the configured timeout
- **THEN** the loop exits with a logged warning and the handler is ready for the next turn

### Requirement: Graceful Shutdown

When the conversation handler is asked to stop, it SHALL cancel its sender task, close the websocket, flush queued audio playback, and release the motion subsystem's listening lock.

#### Scenario: Stop closes the stream and underlying media pipelines

- **GIVEN** an active `LocalStream` with an open recorder/player and a connected handler
- **WHEN** `stop()` is called
- **THEN** the recorder and player pipelines are stopped
- **AND** the handler's sender task is cancelled
- **AND** the websocket is closed

#### Scenario: Stop flushes queued playback

- **GIVEN** queued assistant audio in the player's appsrc
- **WHEN** the stream is stopped
- **THEN** the appsrc is flushed and queued audio is dropped within one frame

## Implementation Anchors

| Concept | Source |
|---------|--------|
| `ConversationHandler` ABC | `src/reachy_mini_conversation_app/conversation_handler.py` |
| `BaseRealtimeHandler` | `src/reachy_mini_conversation_app/base_realtime.py` |
| `OpenAIRealtimeHandler` | `src/reachy_mini_conversation_app/openai_realtime.py` |
| `GeminiLiveHandler` | `src/reachy_mini_conversation_app/gemini_live.py` |
| `HuggingFaceRealtimeHandler` | `src/reachy_mini_conversation_app/huggingface_realtime.py` |
| Backend selection | `src/reachy_mini_conversation_app/config.py` (`get_backend_choice`, `_normalize_backend_provider`, `is_gemini_model`) |
| HF connection-mode logic | `config.py` (`get_hf_connection_selection`, `parse_hf_direct_target`, `build_hf_direct_ws_url`) |
| Audio frame normalization to 1-D mono _(2026-05-14, `e36cded`)_ | `base_realtime.py` (`BaseRealtimeHandler.receive`, reshape block around the `audio_frame.ndim == 2` branch) |
| Silent-microphone diagnostic _(2026-05-14, `e36cded`)_ | `base_realtime.py` (`BaseRealtimeHandler.receive`, `_audio_silence_checked` one-shot guard) |
| OpenAI server-VAD tuning _(2026-05-14, `e36cded`)_ | `openai_realtime.py` (`OpenaiRealtimeHandler` session-config `ServerVad(threshold=0.3, prefix_padding_ms=300, silence_duration_ms=500, …)`) |
| Local audio stream | `src/reachy_mini_conversation_app/console.py` (`LocalStream`) |
