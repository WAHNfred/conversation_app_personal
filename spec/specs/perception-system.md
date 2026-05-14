# Spec: Perception System (Camera, Vision, Head Tracking)

## Purpose

Defines how the robot perceives its environment: camera capture, head tracking, and visual question-answering. This capability owns:

- The `CameraWorker` thread, frame buffering, and graceful shutdown.
- Two head-tracking backend implementations selectable at startup (`yolo`, `mediapipe`).
- The on-device local VLM pipeline (SmolVLM2) and its automatic device selection (CUDA / MPS / CPU).
- The `camera` LLM tool's two execution modes: backend-vision (default) and local-vision (`--local-vision`).
- Frame encoding helpers used to feed snapshots into realtime backends.

Head tracking *application* (whether offsets blend into pose) is covered in [motion-system](motion-system.md). This capability covers *production* of those offsets (detection, frame capture, model inference).

## Requirements

### Requirement: Camera Worker is Optional

The camera subsystem SHALL be enabled by default and SHALL be disabled by the `--no-camera` CLI flag. When disabled, the camera-dependent tools (`camera`, `head_tracking`) MUST be hidden from the LLM session.

#### Scenario: Default startup enables the camera worker

- **GIVEN** the app starts without `--no-camera`
- **WHEN** initialization completes
- **THEN** a `CameraWorker` thread is running and buffering frames
- **AND** `camera` is present in the session tool spec

#### Scenario: --no-camera disables camera and dependent tools

- **GIVEN** the app starts with `--no-camera`
- **WHEN** initialization completes
- **THEN** no `CameraWorker` is started
- **AND** neither `camera` nor `head_tracking` appears in the session tool spec

### Requirement: Frame Buffering

The `CameraWorker` SHALL maintain a single-slot frame buffer with thread-safe access so consumers always read the most recent frame and never block the capture loop.

#### Scenario: Consumer reads most recent frame

- **GIVEN** the camera is producing frames at its native rate
- **WHEN** a consumer thread reads the buffer
- **THEN** it receives the latest captured frame
- **AND** the worker thread is not blocked by the read

#### Scenario: Stale frames are overwritten

- **GIVEN** a consumer has not read for several capture cycles
- **WHEN** the worker captures a new frame
- **THEN** the new frame replaces the previous unread frame in the buffer

### Requirement: Head Tracker Backend Selection

The head tracker SHALL be selectable at startup via `--head-tracker {yolo, mediapipe}`. The system MUST require the matching optional extra to be installed; otherwise startup MUST fail with a clear error.

#### Scenario: YOLO backend uses out-of-process tracker

- **GIVEN** the app starts with `--head-tracker yolo`
- **AND** the `yolo_vision` extra is installed
- **WHEN** the camera worker initializes
- **THEN** a child subprocess is started running the YOLO tracker
- **AND** the parent thread receives tracker results via the IPC queue

#### Scenario: MediaPipe backend uses in-process tracker via toolbox

- **GIVEN** the app starts with `--head-tracker mediapipe`
- **AND** the `mediapipe_vision` extra is installed
- **WHEN** the camera worker initializes
- **THEN** a `MediapipeHeadTracker` is constructed lazily from `reachy_mini_toolbox`
- **AND** detected positions feed the secondary motion channel

#### Scenario: Missing extra fails fast

- **GIVEN** the app starts with `--head-tracker yolo`
- **AND** the `yolo_vision` extra is NOT installed
- **WHEN** initialization runs
- **THEN** startup fails with an error pointing to the missing dependency

### Requirement: Head Tracker Process Lifecycle

The YOLO tracker subprocess SHALL start, signal readiness, deliver tracker-result payloads, and tear down cleanly when the camera worker stops.

#### Scenario: YOLO subprocess signals ready

- **GIVEN** the YOLO subprocess has been spawned
- **WHEN** it finishes model load
- **THEN** the parent observes the ready signal before consuming tracker results

#### Scenario: Tracker result payloads are typed

- **GIVEN** the subprocess emits a payload
- **WHEN** `_is_tracker_result` is called on it
- **THEN** payloads that match the result shape are accepted
- **AND** unexpected payloads are rejected without crashing the worker

### Requirement: Camera Tool Two Modes

The `camera` LLM tool SHALL operate in either (a) **backend-vision mode**: forward the frame to the realtime backend's vision channel, or (b) **local-vision mode**: run inference on the local `VisionProcessor` (SmolVLM2). Mode is selected at startup by the `--local-vision` flag.

#### Scenario: Backend vision via Gemini Live

- **GIVEN** the app runs with the Gemini backend and `--local-vision` is NOT set
- **WHEN** the assistant invokes `camera(question="What do you see?")`
- **THEN** the latest frame is encoded as JPEG via `encode_bgr_frame_as_jpeg`
- **AND** pushed into the Gemini Live session as a video input
- **AND** the tool returns a JSON acknowledgment so the LLM continues the turn

#### Scenario: Local vision with SmolVLM2

- **GIVEN** the app runs with `--local-vision` and the `local_vision` extra installed
- **WHEN** the assistant invokes `camera(question="What color is the cup?")`
- **THEN** the frame is processed by the local `VisionProcessor` using SmolVLM2
- **AND** the textual answer is returned directly to the LLM as the tool result

### Requirement: Local Vision Device Selection

The `VisionProcessor` SHALL select an inference device based on the configured preference. The `auto` mode SHALL prefer MPS on Apple Silicon, then CUDA, then CPU.

#### Scenario: Auto mode prefers MPS on Apple Silicon

- **GIVEN** `VisionConfig.device='auto'` on Apple Silicon
- **WHEN** the processor initializes
- **THEN** the model is loaded on the MPS device

#### Scenario: Auto mode prefers CUDA over CPU

- **GIVEN** `VisionConfig.device='auto'` on a CUDA-capable host without MPS
- **WHEN** the processor initializes
- **THEN** the model is loaded on the CUDA device

#### Scenario: CUDA initialization uses bfloat16 without extra attention wiring

- **GIVEN** the processor initializes on CUDA
- **WHEN** the model is loaded
- **THEN** it is loaded with `torch.bfloat16` dtype
- **AND** no additional attention wrappers are configured

### Requirement: Local Vision Inference Contract

`VisionProcessor.process_image(bgr_frame, prompt)` SHALL accept a BGR frame and a non-empty prompt, run inference, and return a textual description. Failures MUST be reported with structured errors and SHALL be retried once on transient transfer errors.

#### Scenario: Successful inference returns text

- **GIVEN** an initialized `VisionProcessor`
- **WHEN** `process_image(frame, "describe this")` is called
- **THEN** a non-empty string description is returned

#### Scenario: Empty prompt is rejected

- **GIVEN** an initialized `VisionProcessor`
- **WHEN** `process_image(frame, "")` is called
- **THEN** an error is returned describing the missing prompt
- **AND** no model inference is performed

#### Scenario: Retry on transient input transfer failure

- **GIVEN** the first attempt fails because moving inputs to the inference device raised
- **WHEN** the processor retries
- **THEN** the second attempt succeeds and returns the description

#### Scenario: Uninitialized processor returns structured error

- **GIVEN** model load failed during construction
- **WHEN** `process_image` is called
- **THEN** an error JSON is returned identifying the uninitialized state
- **AND** no Python exception escapes the tool

### Requirement: Frame Encoding for Backend Streaming

The system SHALL encode BGR frames to JPEG bytes via `encode_bgr_frame_as_jpeg` for transport to Gemini Live or any backend that consumes JPEG snapshots, throttled to ~1 FPS to preserve bandwidth.

#### Scenario: JPEG bytes are well-formed

- **GIVEN** a BGR frame from the camera worker
- **WHEN** `encode_bgr_frame_as_jpeg(frame)` is called
- **THEN** the returned bytes start with the JPEG magic header and can be decoded by any standard JPEG reader

#### Scenario: Gemini Live receives ~1 FPS

- **GIVEN** Gemini Live is the active backend with the camera tool armed
- **WHEN** a continuous-vision session runs for 10 seconds
- **THEN** roughly 10 frames are forwarded to the Gemini Live session (within tolerance)
- **AND** the audio stream remains uninterrupted

### Requirement: Restricted Platforms for Local Vision

The `--local-vision` flag SHALL NOT be supported when running directly on the Reachy Mini Wireless / Raspberry Pi target. The CLI MUST surface this restriction clearly at startup.

#### Scenario: Local-vision on Pi prints guidance and exits

- **GIVEN** the app is started on the robot's Raspberry Pi target with `--local-vision`
- **WHEN** initialization runs
- **THEN** the app exits with an explanatory message recommending running the conversation app from a laptop while the daemon stays on the robot

## Implementation Anchors

| Concept | Source |
|---------|--------|
| `CameraWorker` | `src/reachy_mini_conversation_app/camera_worker.py` |
| Camera frame encoding | `src/reachy_mini_conversation_app/camera_frame_encoding.py` (`encode_bgr_frame_as_jpeg`) |
| `HeadTracker` protocol | `src/reachy_mini_conversation_app/vision/head_tracking/` |
| YOLO head tracker | `vision/head_tracking/yolo_process.py` (`_build_tracker_backend`, `_is_tracker_result`, subprocess `main`) |
| MediaPipe head tracker | `vision/head_tracking/mediapipe.py` (`MediapipeHeadTracker`) |
| Local VLM | `src/reachy_mini_conversation_app/vision/local_vision.py` (`VisionConfig`, `VisionProcessor`, `initialize_vision_processor`) |
| `camera` tool | `src/reachy_mini_conversation_app/tools/camera.py` (`Camera`) |
| Gemini frame pump | `gemini_live.py` (continuous-vision sender at ~1 FPS) |
