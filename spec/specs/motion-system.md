# Spec: Motion System

## Purpose

Defines the robot's motion subsystem: how speech, conversation tools, head-tracking, and idle behavior are blended into a single coherent stream of pose commands at ~100 Hz. This capability owns:

- The `MovementManager` and its dedicated worker thread.
- The two-channel blend model: **primary** moves (mutually exclusive, queued) and **secondary** moves (additive, continuous).
- Primary move types: `BreathingMove`, `DanceQueueMove`, `EmotionQueueMove`, `GotoQueueMove`.
- Secondary inputs: speech-reactive head wobble (covered in [perception-system](perception-system.md) only for camera; speech wobble is owned here) and head-tracking offsets.
- The seven motion-related LLM tools: `move_head`, `dance`, `stop_dance`, `play_emotion`, `stop_emotion`, `head_tracking` (state-only).

The motion subsystem is the most timing-sensitive part of the app. Anything that fights the control loop or its blending invariants is a bug.

## Requirements

### Requirement: Primary / Secondary Blend Model

Pose at time `t` SHALL be computed as `combine_full_body(primary_pose(t), secondary_offsets(t))`. Primary moves are mutually exclusive; secondary offsets are additive deltas applied on top.

#### Scenario: Dance and head-tracking compose without conflict

- **GIVEN** a `DanceQueueMove` is running as primary
- **AND** head-tracking is enabled with a non-zero detected offset
- **WHEN** the control loop ticks
- **THEN** the emitted pose is the dance's pose plus the tracking offset
- **AND** the dance trajectory is not modified in place

#### Scenario: Speech-reactive wobble is additive

- **GIVEN** a `BreathingMove` is running as primary
- **AND** the speech-reactive wobbler emits a head Y-offset of 0.05 rad
- **WHEN** the control loop ticks
- **THEN** the breathing pose receives the wobble offset additively

### Requirement: Sequential Primary Move Queue

The primary move queue SHALL execute one move at a time. New primary moves SHALL be appended; they MUST NOT preempt the running one unless `stop()` is called.

#### Scenario: Queue plays moves in order

- **GIVEN** an empty primary queue
- **WHEN** `dance("happy")` is enqueued, then `play_emotion("curious")` is enqueued
- **THEN** the dance completes before the emotion begins

#### Scenario: Stop clears running and queued moves

- **GIVEN** a running primary move with two queued moves behind it
- **WHEN** `stop_dance` is invoked
- **THEN** the running move is cancelled
- **AND** the two queued moves are discarded
- **AND** the manager returns to the idle behavior (breathing)

### Requirement: Idle Breathing

When the primary queue is empty and the robot has been inactive longer than the configured idle delay, the system SHALL start a `BreathingMove` automatically. Breathing SHALL transition smoothly from the last held pose into the breathing pattern.

#### Scenario: Breathing starts after idle delay

- **GIVEN** the queue is empty and no move has run in the last idle-delay window
- **WHEN** the control loop ticks
- **THEN** a `BreathingMove` is enqueued automatically
- **AND** it interpolates from the current pose into the breathing baseline

#### Scenario: Activity timer suppresses breathing

- **GIVEN** a tool has just queued a goto move
- **WHEN** the control loop ticks within the idle delay
- **THEN** breathing is NOT auto-started

### Requirement: 100 Hz Control Loop with Frequency Telemetry

The control loop SHALL target 100 Hz and SHALL record rolling frequency statistics for observability. Loop sleep time MUST adapt to maintain the target frequency.

#### Scenario: Loop maintains target frequency

- **GIVEN** a `MovementManager` started at 100 Hz
- **WHEN** the worker thread runs for one second
- **THEN** the loop completes approximately 100 iterations
- **AND** the `LoopFrequencyStats` reports a frequency within tolerance of 100 Hz

#### Scenario: Frequency telemetry is observable

- **GIVEN** the loop has run long enough to accumulate statistics
- **WHEN** an external thread reads the status snapshot
- **THEN** it receives a thread-safe copy of the current frequency stats without blocking the loop

### Requirement: Move Protocol

Every primary move SHALL implement an `evaluate(t)` method returning a `FullBodyPose` at time `t`. Wrapper classes adapt third-party move objects (dances, emotions, gotos) to this protocol.

#### Scenario: DanceQueueMove wraps a dance object

- **GIVEN** a dance loaded from `reachy_mini_dances_library`
- **WHEN** `DanceQueueMove(dance).evaluate(t)` is called
- **THEN** it delegates to the wrapped dance's evaluator and returns the pose at `t`

#### Scenario: Linear interpolation for goto moves

- **GIVEN** a `GotoQueueMove` from pose A to pose B over duration D
- **WHEN** `evaluate(t)` is called for `t = 0.5 * D`
- **THEN** the returned pose is the linear midpoint between A and B

### Requirement: Move Head Tool

The `move_head` tool SHALL queue a goto move that transitions the head to a named direction (`left`, `right`, `up`, `down`, `front`) without interrupting the speech-reactive wobble.

#### Scenario: move_head queues a goto

- **GIVEN** the assistant invokes `move_head(direction="left")`
- **WHEN** the tool runs
- **THEN** a `GotoQueueMove` targeting the left preset pose is enqueued as primary
- **AND** the wobbler continues operating as secondary

### Requirement: Dance and Emotion Catalogue Discovery

The `dance` and `play_emotion` tools SHALL fetch their available content lists from the published Hugging Face datasets via the helper functions `get_available_dances_and_descriptions` and `get_available_emotions_and_descriptions`.

#### Scenario: Dance catalogue is exposed in the tool spec

- **GIVEN** the dances library is reachable
- **WHEN** the `dance` tool's function spec is built
- **THEN** the spec's `dance_name` parameter enumerates the available dance names with human-readable descriptions

#### Scenario: Emotion catalogue is exposed in the tool spec

- **GIVEN** the emotions library is reachable
- **WHEN** the `play_emotion` tool's function spec is built
- **THEN** the spec's parameter enumerates the available emotions

### Requirement: Stop Tools

`stop_dance` and `stop_emotion` SHALL cancel the active primary move and clear queued moves of the corresponding kind.

#### Scenario: stop_dance clears dances

- **GIVEN** a running dance with two queued dances behind it
- **WHEN** the assistant invokes `stop_dance`
- **THEN** the running dance ends and the queued dances are discarded

#### Scenario: stop_emotion clears emotions

- **GIVEN** a queued emotion with no other moves
- **WHEN** the assistant invokes `stop_emotion`
- **THEN** the emotion is removed from the queue and the manager returns to idle behavior

### Requirement: Head-Tracking Toggle

The `head_tracking` tool SHALL only toggle the application of head-tracking offsets in the secondary channel. It MUST NOT start or stop the underlying camera tracking subprocess.

#### Scenario: head_tracking enables offset blending

- **GIVEN** the camera worker has a configured head tracker
- **AND** head-tracking offsets are currently disabled
- **WHEN** the assistant invokes `head_tracking(enabled=true)`
- **THEN** future secondary offsets from the tracker are applied to the pose

#### Scenario: head_tracking disables offset blending

- **GIVEN** head-tracking offsets are currently applied
- **WHEN** the assistant invokes `head_tracking(enabled=false)`
- **THEN** the offsets are zeroed in the secondary channel
- **AND** the tracker subprocess continues running but its output is ignored

### Requirement: Speech-Reactive Head Wobble

While the assistant is speaking, the `HeadWobbler` SHALL convert assistant audio (PCM or base64-encoded deltas) into smooth head-position offsets in the secondary channel, with thread-safe ingestion from the audio thread.

#### Scenario: Audio deltas drive head offset

- **GIVEN** the assistant is speaking and the wobbler has received audio deltas
- **WHEN** the control loop polls the wobbler
- **THEN** a non-zero secondary head offset is returned, derived from the audio amplitude

#### Scenario: Wobbler resets after current audio finishes

- **GIVEN** the wobbler has been driven by an audio stream that just ended
- **WHEN** `request_reset_after_current_audio()` is invoked
- **THEN** the wobbler reports `True` from its reset query once the queued audio has drained
- **AND** subsequent polls return zero offsets

#### Scenario: PCM and base64 ingestion are both thread-safe

- **GIVEN** the wobbler is in use
- **WHEN** `feed_pcm` and `feed` (base64) are called concurrently from different threads
- **THEN** no data is lost or corrupted, and the consumer queue remains consistent

### Requirement: Listening Mode Holds the Head Steady

While the user is speaking, the motion manager SHALL freeze the head in a "listening" hold so the robot visibly attends to the user. Background tools completing during listening MUST NOT release the hold.

#### Scenario: Listening freezes secondary motion

- **GIVEN** the user begins speaking
- **WHEN** `set_listening(True)` is called
- **THEN** the secondary speech offsets are clamped to a steady listening pose
- **AND** subtle antennae blending remains active

#### Scenario: Tool completion does not exit listening

- **GIVEN** the user is speaking and listening mode is engaged
- **WHEN** a background tool completes
- **THEN** listening mode remains engaged until the user stops speaking

## Implementation Anchors

| Concept | Source |
|---------|--------|
| `MovementManager` and control loop | `src/reachy_mini_conversation_app/moves.py` |
| `Move`, `BreathingMove`, full-body composition | `moves.py` (`combine_full_body`, `clone_full_body_pose`, `MovementState`) |
| Loop frequency telemetry | `moves.py` (`LoopFrequencyStats`) |
| Dance/Emotion/Goto wrappers | `src/reachy_mini_conversation_app/dance_emotion_moves.py` (`DanceQueueMove`, `EmotionQueueMove`, `GotoQueueMove`) |
| `HeadWobbler` (speech-reactive) | `src/reachy_mini_conversation_app/audio/head_wobbler.py` |
| Speech tapper (audio signal) | `src/reachy_mini_conversation_app/audio/speech_tapper.py` |
| Built-in motion tools | `tools/move_head.py`, `tools/dance.py`, `tools/play_emotion.py`, `tools/stop_dance.py`, `tools/stop_emotion.py`, `tools/head_tracking.py` |
| Dance catalogue helper | `tools/dance.py` (`get_available_dances_and_descriptions`) |
| Emotion catalogue helper | `tools/play_emotion.py` (`get_available_emotions_and_descriptions`) |
