# Spec: User Interfaces (Console, Gradio, Headless Settings)

## Purpose

Defines the surfaces through which the user interacts with the running app. This capability owns:

- The default **console mode** (`LocalStream` + terminal logs).
- The **Gradio Web UI** (`--gradio`) hosting the live conversation surface, the Personality accordion, and the Settings panel.
- The **headless settings UI** mounted as FastAPI routes (so a settings UI exists even in console mode for browser-based credential entry).
- The **JavaScript frontend** wired into the Gradio static `index.html` for backend selection, voice selection, and personality apply.
- Live transcript updates into the chat surface.

UI behavior delegates business logic to the other capabilities. Selection rules belong to [conversation-and-backends](conversation-and-backends.md); profile mechanics belong to [personality-system](personality-system.md).

## Requirements

### Requirement: Default Console Mode

When the app is launched without `--gradio`, it SHALL run in console mode using `LocalStream` to capture microphone input through Reachy Mini's recorder and play assistant audio through the robot's player.

#### Scenario: Console mode starts a local stream

- **GIVEN** the app is launched without `--gradio`
- **WHEN** initialization completes
- **THEN** a `LocalStream` instance is constructed using the robot's recorder and player
- **AND** stdin remains available for keyboard-driven shutdown (Ctrl+C)

#### Scenario: Console mode supports headless settings

- **GIVEN** the app runs in console mode
- **WHEN** the user opens the settings URL in a browser
- **THEN** the FastAPI-mounted settings UI loads
- **AND** changes made there persist to the instance `.env` and refresh runtime config

### Requirement: Gradio Web UI

When launched with `--gradio`, the app SHALL serve a Gradio app at `http://127.0.0.1:7860/` containing: a conversation surface (chatbot + audio + optional webcam), a Personality accordion, and a Settings panel.

#### Scenario: Gradio surfaces personality controls

- **GIVEN** the app is launched with `--gradio`
- **WHEN** the user opens the Personality accordion
- **THEN** a dropdown lists available profiles
- **AND** an instructions textarea shows the active profile's instructions
- **AND** an Apply button is enabled (unless `LOCKED_PROFILE` is set)

#### Scenario: Gradio is required for simulation mode

- **GIVEN** simulation mode is selected
- **WHEN** the app launches without `--gradio`
- **THEN** the app exits with a message explaining that `--gradio` is required for simulation

### Requirement: Conversation Surface Live Updates

The chatbot widget SHALL receive incremental updates from the realtime handler's `update_chatbot` callback. Each finalized turn MUST appear as exactly one message in the chatbot.

#### Scenario: User and assistant turns are appended in order

- **GIVEN** the conversation surface is empty
- **WHEN** the user speaks one turn and the assistant responds
- **THEN** the chatbot shows two messages in order: user, then assistant
- **AND** each message contains its finalized transcript

### Requirement: Backend Switching in Settings UI

The Settings UI SHALL allow switching backend providers, entering credentials, and (for Hugging Face) selecting connection mode. Saves MUST persist to the instance `.env`, MUST refresh runtime config, and MUST NOT clobber an explicit `MODEL_NAME` override.

#### Scenario: Saving a model name persists to env

- **GIVEN** the OpenAI backend is selected
- **WHEN** the user enters a custom `MODEL_NAME` and saves
- **THEN** the value is persisted to the instance `.env`
- **AND** subsequent reads via `get_model_name_for_backend()` return the override

#### Scenario: Saving credentials does not reset custom model override

- **GIVEN** a custom `MODEL_NAME` is already saved
- **WHEN** the user updates only `OPENAI_API_KEY`
- **THEN** the saved `MODEL_NAME` remains untouched
- **AND** future sessions still use the custom model

#### Scenario: Switching to Gemini persists choice and token

- **GIVEN** the user selects Gemini in the Settings UI
- **AND** enters a `GEMINI_API_KEY`
- **WHEN** they save
- **THEN** both `BACKEND_PROVIDER=gemini` and the key are written to `.env`
- **AND** `refresh_runtime_config_from_env` reflects the new backend in `get_backend_choice()`

#### Scenario: Hugging Face local URL is validated

- **GIVEN** the Settings UI is set to Hugging Face local mode
- **WHEN** the user enters an invalid port (out of range)
- **THEN** the save is rejected with an error referencing the invalid port

#### Scenario: Persisted direct Hugging Face websocket is reused

- **GIVEN** a previously saved direct Hugging Face websocket URL
- **WHEN** the user switches back to a local Hugging Face mode without re-entering the URL
- **THEN** the persisted URL is reused

### Requirement: Headless Settings UI Always Available

In both console and Gradio modes, a settings UI SHALL be mounted as FastAPI routes so the user can configure the app from a browser even when the conversation runs in console mode.

#### Scenario: Settings routes are mounted in console mode

- **GIVEN** the app is in console mode
- **WHEN** it serves the FastAPI app
- **THEN** the `mount_personality_routes` and the audio-settings routes are reachable

#### Scenario: Voice change via query param applies live

- **GIVEN** the headless settings UI is loaded
- **WHEN** the user posts a voice change via a query param
- **THEN** the active voice updates for the live session
- **AND** the change is reflected in the next assistant turn

### Requirement: Audio Stream Behavior

`LocalStream` SHALL support both WebRTC (Gradio) audio and the local GStreamer recorder/player. When local audio is in use, the player SHALL flush queued playback via the appsrc API on stop. When WebRTC is in use, the output buffer API SHALL be used.

#### Scenario: Local GStreamer flush on stop

- **GIVEN** local GStreamer audio is active with queued audio
- **WHEN** `stop()` is called
- **THEN** the player's appsrc is flushed to drop queued audio
- **AND** the recorder pipeline is stopped

#### Scenario: WebRTC flush on stop

- **GIVEN** WebRTC audio is active with queued playback
- **WHEN** the stream stops
- **THEN** the output buffer is flushed via the WebRTC output API

### Requirement: Backend Selection Validation in JS Frontend

The JS frontend SHALL prevent starting a conversation when the selected backend lacks its required credentials, and SHALL surface the missing credential to the user.

#### Scenario: OpenAI start blocked without API key

- **GIVEN** the user selects OpenAI in the UI
- **AND** no `OPENAI_API_KEY` is set
- **WHEN** the user attempts to start the conversation
- **THEN** `backendCanProceed()` returns false
- **AND** the UI shows a message identifying the missing credential
- **AND** the start request is not sent

#### Scenario: HF deployed selection always proceeds

- **GIVEN** the user selects Hugging Face deployed mode
- **WHEN** the user starts the conversation
- **THEN** `backendCanProceed()` returns true even with no API keys configured

#### Scenario: HF direct websocket selection is valid

- **GIVEN** the user enters a direct websocket URL in the local Hugging Face form
- **WHEN** validation runs
- **THEN** a well-formed `ws://host:port/...` URL is accepted as a valid configuration

### Requirement: Headless Personality UI Tool Listing

The headless personality UI SHALL expose the default tool list on initial load (so the UI shows what would be enabled before the user picks a profile) and SHALL expose backend-specific voices when querying voices.

#### Scenario: Initial load shows default tools

- **GIVEN** the headless personality UI is opened
- **WHEN** the page fetches the default tool list
- **THEN** the built-in `default/tools.txt` entries are returned

#### Scenario: Voice list reflects active backend

- **GIVEN** Gemini is the active backend
- **WHEN** the UI requests voices
- **THEN** the response contains Gemini voices
- **AND** OpenAI voices are not returned

### Requirement: Saving Startup Personality Persists Manual Voice Override

When the user saves a startup personality, any active manual voice override SHALL also be persisted as the startup voice.

#### Scenario: Save persists both profile and current voice

- **GIVEN** the user has applied profile `chess_coach` and manually set voice `nova`
- **WHEN** they click "Save as startup"
- **THEN** `startup_settings.json` records both `chess_coach` and `nova`

## Implementation Anchors

| Concept | Source |
|---------|--------|
| Console main loop | `src/reachy_mini_conversation_app/console.py` (`LocalStream`, the entrypoint) |
| Gradio personality UI | `src/reachy_mini_conversation_app/gradio_personality.py` (`PersonalityUI`) |
| Headless personality UI (FastAPI routes) | `src/reachy_mini_conversation_app/headless_personality_ui.py` (`mount_personality_routes`) |
| JS frontend | `src/reachy_mini_conversation_app/static/main.js`, `static/index.html` (`applyPersonality`, `applyVoice`, `BACKEND_META`, `backendCanProceed`, `backendHasCredentials`) |
| Chatbot update callback | `src/reachy_mini_conversation_app/main.py` (`update_chatbot`) |
| Backend-specific voices | `config.py` (`get_available_voices_for_backend`, `get_default_voice_for_backend`) |
