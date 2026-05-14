# Spec: Configuration & Runtime

## Purpose

Defines how the app reads, validates, and refreshes its configuration. This capability owns:

- The `.env` lifecycle: template → instance file → in-memory environment.
- Persistence helpers that write values back to the instance `.env` and refresh runtime config.
- The startup environment fallback chain (`LOCKED_PROFILE` → saved settings → `REACHY_MINI_CUSTOM_PROFILE` → `default`).
- Name-collision protection at startup (covered behaviorally in [tool-system](tool-system.md), implemented here).
- Optional override surfaces: model name, voice, Hugging Face URL, external content directories.
- The CLI flag set parsed by `main.py`.
- The Reachy Mini audio startup configuration (`apply_audio_startup_config`) applied once at boot.
- The `--robot-name` selector for multi-robot subnets.

Configuration is a flat read-mostly layer. Mutating it MUST go through the persistence helpers so the in-memory environment and the instance `.env` stay in sync.

## Requirements

### Requirement: `.env` Layering

The runtime configuration SHALL be derived from three sources merged in order: (1) process environment, (2) instance-local `.env`, (3) repo-shipped `.env.example` template for defaults. Values closer to the top take precedence.

#### Scenario: Instance `.env` overrides repo template

- **GIVEN** `.env.example` has `BACKEND_PROVIDER=huggingface`
- **AND** the instance `.env` has `BACKEND_PROVIDER=openai`
- **WHEN** configuration loads
- **THEN** `get_backend_choice()` returns `openai`

#### Scenario: Process environment overrides instance `.env`

- **GIVEN** the instance `.env` has `MODEL_NAME=foo`
- **AND** the process environment has `MODEL_NAME=bar`
- **WHEN** configuration loads
- **THEN** `get_model_name_for_backend()` returns `bar`

### Requirement: Persistence Helpers Are Atomic

When persisting a value, the helper SHALL write to the instance `.env` and update the in-memory process environment so subsequent reads observe the change without restart.

#### Scenario: Persisting an API key updates env

- **GIVEN** the user submits `OPENAI_API_KEY=sk-...`
- **WHEN** the persistence helper runs
- **THEN** the value is written to the instance `.env`
- **AND** `os.environ["OPENAI_API_KEY"]` reflects the new value in the same process

#### Scenario: Persisting empty value removes the key

- **GIVEN** a previously persisted `HF_REALTIME_WS_URL`
- **WHEN** the persistence helper is called with an empty value
- **THEN** the key is removed from the instance `.env`
- **AND** the in-memory environment no longer contains the key

#### Scenario: refresh_runtime_config_from_env picks up changes

- **GIVEN** a `BACKEND_PROVIDER` change has been persisted
- **WHEN** `refresh_runtime_config_from_env()` is called
- **THEN** the mutable runtime config object reflects the new backend

### Requirement: CLI Flag Set

The CLI SHALL accept the following flags, all optional, all with the documented defaults:

- `--head-tracker {yolo, mediapipe}` (default: none).
- `--no-camera` (default: false).
- `--local-vision` (default: false).
- `--gradio` (default: false).
- `--robot-name <name>` (default: none).
- `--debug` (default: false; enables verbose logging).

#### Scenario: Default flags result in console mode with camera

- **GIVEN** the app is launched with no flags
- **WHEN** initialization runs
- **THEN** the app is in console mode (`--gradio` false)
- **AND** the camera worker is active (`--no-camera` false)
- **AND** no head tracker is configured

#### Scenario: --robot-name selects a specific daemon

- **GIVEN** two Reachy Mini daemons on the same subnet, named `kitchen` and `lab`
- **WHEN** the app is launched with `--robot-name lab`
- **THEN** the SDK connects to the `lab` daemon
- **AND** does not connect to `kitchen`

#### Scenario: --debug enables verbose logging

- **GIVEN** the app is launched with `--debug`
- **WHEN** logging is configured
- **THEN** the log level is `DEBUG`
- **AND** the audio pipeline still meets its low-latency targets

### Requirement: Startup Profile Resolution Chain

The active profile at startup SHALL be resolved in priority order:

1. `LOCKED_PROFILE` constant in `config.py` (if not `None`).
2. Saved startup settings (`startup_settings.json`).
3. Environment variable `REACHY_MINI_CUSTOM_PROFILE`.
4. The `default` profile.

#### Scenario: Locked profile beats every other source

- **GIVEN** `LOCKED_PROFILE = "mars_rover"`
- **AND** `startup_settings.json` says `chess_coach`
- **AND** `REACHY_MINI_CUSTOM_PROFILE=time_traveler`
- **WHEN** the app starts
- **THEN** the active profile is `mars_rover`

#### Scenario: Saved settings beat env when not locked

- **GIVEN** `LOCKED_PROFILE` is `None`
- **AND** `startup_settings.json` says `chess_coach`
- **AND** `REACHY_MINI_CUSTOM_PROFILE=time_traveler`
- **WHEN** the app starts
- **THEN** the active profile is `chess_coach`

#### Scenario: Env fallback when no saved settings

- **GIVEN** `LOCKED_PROFILE` is `None`
- **AND** no saved startup settings exist
- **AND** `REACHY_MINI_CUSTOM_PROFILE=time_traveler` is set
- **WHEN** the app starts
- **THEN** the active profile is `time_traveler`

#### Scenario: Default fallback when nothing is configured

- **GIVEN** none of the above sources select a profile
- **WHEN** the app starts
- **THEN** the active profile is `default`

### Requirement: External Content Directories

When `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY` and/or `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` are set, the app SHALL include those directories in profile listing, profile loading, and tool resolution.

#### Scenario: External profile referenced via env

- **GIVEN** `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=./ext`
- **AND** `./ext/myprofile/` contains `instructions.txt`
- **AND** `REACHY_MINI_CUSTOM_PROFILE=myprofile`
- **WHEN** the app starts (and is not locked)
- **THEN** `myprofile` is loaded as the active profile

#### Scenario: External profile missing from disk fails

- **GIVEN** `REACHY_MINI_CUSTOM_PROFILE=missing_profile`
- **AND** the named profile does not exist in any configured root
- **WHEN** the app starts
- **THEN** startup fails with an error naming the missing profile

### Requirement: Name Collision Protection at Startup

The configuration loader SHALL refuse to start if any of these collisions exist:

- An external tool module name matches a built-in tool module name.
- An external profile folder name matches a built-in profile folder name (compact name comparison).
- Any selected profile name appears in neither the built-in nor the external profiles root.

#### Scenario: Profile selected but absent from external root

- **GIVEN** `REACHY_MINI_CUSTOM_PROFILE=ghost_profile`
- **AND** `ghost_profile` is not in any profiles root
- **WHEN** the app starts
- **THEN** startup fails fast with a clear missing-profile error

### Requirement: Reachy Mini Audio Startup Configuration

On boot, the system SHALL apply the tuned XVF3800 audio startup configuration via `apply_audio_startup_config` before the realtime stream opens.

#### Scenario: Audio startup runs once at boot

- **GIVEN** the app is starting up
- **WHEN** the audio subsystem initializes
- **THEN** `apply_audio_startup_config` is called exactly once
- **AND** the config values are logged via `_format_config`

#### Scenario: Audio startup is observable in tests via fake wrapper

- **GIVEN** a `FakeAudio` SDK wrapper is injected
- **WHEN** the startup configuration is applied
- **THEN** the fake wrapper records the configuration calls in the expected order

### Requirement: Media Backend Fallback Chain _(2026-05-14, `e36cded`)_

When `ReachyMini` cannot be initialized with the default media backend, the app SHALL attempt a deterministic fallback chain instead of failing outright. The chain is: **default (GStreamer)** → **`sounddevice_opencv`** → **`sounddevice_no_video`**. The system MUST log each fallback transition at warning level so the operator can see which backend ended up active. Only when all three backends fail SHALL the app exit with a non-zero status.

This requirement enables the conversation app to run on the two non-Wireless targets: **Reachy Lite** (no GObject Introspection / `gi` module installed) and laptop / desktop development machines (no physical camera or no GStreamer).

#### Scenario: Missing `gi` module falls through to `sounddevice_opencv`

- **GIVEN** the app starts on a host without the `gi` Python module
- **WHEN** `ReachyMini(...)` raises an `ImportError` whose message mentions `gi` or `gstreamer`
- **THEN** the app logs a warning naming the missing backend
- **AND** retries with `media_backend="sounddevice_opencv"`
- **AND** continues startup if the retry succeeds

#### Scenario: Missing camera falls through to `sounddevice_no_video`

- **GIVEN** the `sounddevice_opencv` retry has been triggered (per the previous scenario)
- **WHEN** that retry fails (typically because no physical camera is attached)
- **THEN** the app logs a second warning naming the failure
- **AND** retries with `media_backend="sounddevice_no_video"`
- **AND** continues startup with audio-only if the third attempt succeeds

#### Scenario: All three backends fail aborts startup

- **GIVEN** the default, `sounddevice_opencv`, and `sounddevice_no_video` initializations have all failed
- **WHEN** the third exception is observed
- **THEN** the app logs an error summarising all-backend failure
- **AND** exits with status code 1

#### Scenario: Non-GStreamer ImportError is not treated as a backend issue

- **GIVEN** the default `ReachyMini(...)` raises an `ImportError` whose message does not mention `gi` or `gstreamer`
- **WHEN** the error handler runs
- **THEN** no media-backend fallback is attempted
- **AND** the app exits with a generic initialization error

### Requirement: Hugging Face URL Parsing

The system SHALL parse Hugging Face realtime URLs into OpenAI-compatible endpoint components consumed by the client builder.

#### Scenario: Base URL is expanded to realtime path

- **GIVEN** the user provided `ws://127.0.0.1:8765/v1`
- **WHEN** `parse_hf_realtime_url` runs
- **THEN** the parsed components include host, port, and the realtime path
- **AND** `_build_openai_compatible_client_from_realtime_url` constructs a working client

#### Scenario: Full realtime URL passes through unchanged

- **GIVEN** the user provided `ws://127.0.0.1:8765/v1/realtime`
- **WHEN** parsing runs
- **THEN** the resolved client URL is identical to the input

### Requirement: Env Flag Parsing

Boolean environment flags SHALL accept `1`, `true`, `yes`, `on` (case-insensitive) as truthy and `0`, `false`, `no`, `off` (and empty) as falsy. Unknown values SHALL be treated as falsy.

#### Scenario: AUTOLOAD_EXTERNAL_TOOLS truthy values

- **GIVEN** `AUTOLOAD_EXTERNAL_TOOLS` set to `1`, `true`, `yes`, or `on` (any case)
- **WHEN** `_env_flag` parses it
- **THEN** the result is `True`

#### Scenario: Empty or missing flag is falsy

- **GIVEN** `AUTOLOAD_EXTERNAL_TOOLS` is unset or empty
- **WHEN** `_env_flag` parses it
- **THEN** the result is `False`

### Requirement: Hugging Face Cache Directory

`HF_HOME` SHALL be honored when `--local-vision` is active and SHALL default to `./cache` relative to the working directory.

#### Scenario: Default cache directory

- **GIVEN** `--local-vision` is enabled and `HF_HOME` is unset
- **WHEN** the vision model is downloaded
- **THEN** the cache path resolves to `./cache`

#### Scenario: Custom cache directory

- **GIVEN** `HF_HOME=/data/hf` is set
- **AND** `--local-vision` is enabled
- **WHEN** the vision model is downloaded
- **THEN** files are written under `/data/hf`

## Implementation Anchors

| Concept | Source |
|---------|--------|
| Main config module | `src/reachy_mini_conversation_app/config.py` |
| CLI argparse + entrypoint | `src/reachy_mini_conversation_app/main.py`, `src/reachy_mini_conversation_app/utils.py` |
| Locked profile constant | `config.py` (`LOCKED_PROFILE`) |
| Backend / model resolution | `config.py` (`get_backend_choice`, `get_backend_label`, `is_gemini_model`, `get_model_name_for_backend`, `_resolve_model_name`) |
| HF URL parsing | `config.py` (`HFRealtimeURLParts`, `parse_hf_direct_target`, `parse_hf_realtime_url`, `build_hf_direct_ws_url`) |
| HF connection resolution | `config.py` (`get_hf_connection_selection`, `get_hf_direct_ws_url`, `get_hf_session_url`, `has_hf_realtime_target`, `_normalize_hf_connection_mode`) |
| Voice selection | `config.py` (`get_available_voices_for_backend`, `get_default_voice_for_backend`) |
| Env persistence helpers | `config.py` (load env file, persist env value(s), persist HF / OpenAI / Gemini tokens, remove keys) |
| Runtime refresh | `config.py` (`refresh_runtime_config_from_env`) |
| Boolean flag parser | `config.py` (`_env_flag`) |
| Source checkout detection | `config.py` (`_is_source_checkout_root`, `_packaged_profiles_directory`) |
| Audio startup configuration | `src/reachy_mini_conversation_app/audio/startup_config.py` (`apply_audio_startup_config`, `_format_config`) |
| Media backend fallback chain _(2026-05-14, `e36cded`)_ | `src/reachy_mini_conversation_app/main.py` (`run`, ImportError handler around `ReachyMini(...)`) |
| Startup settings persistence | `src/reachy_mini_conversation_app/startup_settings.py` |
| Build-time profile packaging | `setup.py` (`BuildPyWithProfiles`) |
