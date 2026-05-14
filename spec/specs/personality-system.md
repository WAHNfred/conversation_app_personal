# Spec: Personality System (Profiles & Prompts)

## Purpose

Defines how personalities are authored, stored, composed, persisted, and applied. This capability owns:

- The on-disk profile format (`profiles/<name>/instructions.txt`, `tools.txt`, optional `voice.txt`, optional `*.py` custom tools).
- Prompt placeholder composition (`[name]` and `[nested/name]` references resolved against `prompts/`).
- Profile discovery and listing for the UI.
- Hot-apply at runtime (sends new system prompt to the active session without dropping the connection).
- Persistence of startup profile and voice in `startup_settings.json`.
- The two profile-source-selection mechanisms: `LOCKED_PROFILE` (compile-time lock) and `REACHY_MINI_CUSTOM_PROFILE` (runtime env fallback).
- External profile directories via `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY`.

This capability is consumed by [conversation-and-backends](conversation-and-backends.md) (which calls `apply_personality` on the active handler) and by [user-interfaces](user-interfaces.md) (which renders the profile selector).

## Requirements

### Requirement: Profile Folder Layout

A profile SHALL live in a folder named `<profile_name>/` containing at minimum an `instructions.txt`. The folder MAY also contain:

- `tools.txt` — newline-separated allowlist of tools (with `#` comments).
- `voice.txt` — single-line voice identifier interpreted by the active backend.
- Zero or more `*.py` files implementing custom `Tool` subclasses.

If `tools.txt` is missing on a built-in profile, the LLM operates with no enabled tools; if missing on an external profile, the built-in `profiles/default/tools.txt` is used as fallback.

#### Scenario: Default profile loads with built-in tools

- **GIVEN** the `profiles/default/` folder with both `instructions.txt` and `tools.txt`
- **WHEN** the app starts with the default profile
- **THEN** the listed tools are enabled and the instructions are used as the system prompt

#### Scenario: External profile without tools.txt falls back to default tools.txt

- **GIVEN** an external profile under `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY/myprofile/` with no `tools.txt`
- **WHEN** the app starts with `REACHY_MINI_CUSTOM_PROFILE=myprofile`
- **THEN** the built-in `profiles/default/tools.txt` is used to determine enabled tools

#### Scenario: Profile-local Python files become available tools

- **GIVEN** a profile `example/` containing `sweep_look.py` with a `SweepLook(Tool)` subclass
- **AND** `tools.txt` includes the line `sweep_look`
- **WHEN** the profile is loaded
- **THEN** the `sweep_look` tool is registered and visible to the LLM

### Requirement: Prompt Placeholder Composition

`instructions.txt` SHALL support inline placeholders of the form `[name]` or `[nested/name]`. At load time, each placeholder MUST be replaced by the content of `src/reachy_mini_conversation_app/prompts/<name>.txt` (with `/` traversal allowed). Nested placeholders SHALL also be resolved recursively up to a finite depth.

#### Scenario: Flat placeholder resolves

- **GIVEN** `instructions.txt` containing `[passion_for_lobster_jokes]`
- **AND** the file `prompts/passion_for_lobster_jokes.txt` exists
- **WHEN** the profile is composed
- **THEN** the placeholder is replaced by the file's content

#### Scenario: Nested placeholder resolves

- **GIVEN** `instructions.txt` containing `[identities/witty_identity]`
- **AND** the file `prompts/identities/witty_identity.txt` exists
- **WHEN** the profile is composed
- **THEN** the placeholder is replaced by the file's content

#### Scenario: Missing placeholder file fails with clear error

- **GIVEN** `instructions.txt` references `[no_such_file]`
- **AND** `prompts/no_such_file.txt` does not exist
- **WHEN** the profile is composed
- **THEN** loading fails with an error naming the missing file

### Requirement: Profile Discovery

The system SHALL discover available profiles from the packaged profiles root (`profiles/` shipped in the wheel) plus the external profiles root when configured. Built-in profiles MUST take precedence on name conflict, except that name collisions are blocked at startup (see [tool-system](tool-system.md)).

#### Scenario: list_personalities returns built-in profiles

- **GIVEN** the packaged profiles root contains 14 built-in profiles
- **WHEN** `list_personalities()` is called
- **THEN** the result includes all 14 profile names plus any external profiles

#### Scenario: External profiles appear in the picker

- **GIVEN** `REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=./external_content/external_profiles` with `starter_profile/` inside
- **WHEN** the app lists personalities
- **THEN** `starter_profile` is included alongside the built-in names

### Requirement: Locked Profile Mode

When `LOCKED_PROFILE` is set to a non-`None` value in `config.py`, the app SHALL force that profile and SHALL ignore: saved startup settings, `REACHY_MINI_CUSTOM_PROFILE`, and any Gradio UI selection. The personality UI MUST visually communicate the locked state and MUST disable editing controls.

#### Scenario: Locked profile overrides startup settings

- **GIVEN** `LOCKED_PROFILE = "mars_rover"` in `config.py`
- **AND** `startup_settings.json` contains a different selected profile
- **WHEN** the app starts
- **THEN** the active profile is `mars_rover`
- **AND** the saved startup setting is ignored

#### Scenario: Locked UI shows the (locked) marker

- **GIVEN** `LOCKED_PROFILE = "mars_rover"`
- **WHEN** the Gradio personality accordion renders
- **THEN** the profile name is displayed with a "(locked)" suffix
- **AND** the profile selector, instructions textarea, and Apply button are disabled

### Requirement: Startup Profile and Voice Persistence

The UI's selected startup profile and active voice SHALL be persisted in an instance-local `startup_settings.json`. On launch, those values SHALL be reloaded if and only if `LOCKED_PROFILE` is not set.

#### Scenario: Saved startup settings are restored

- **GIVEN** the user previously saved profile `chess_coach` and voice `nova`
- **WHEN** the app launches without a `LOCKED_PROFILE`
- **THEN** `chess_coach` is loaded as the active profile
- **AND** voice `nova` is sent in the initial session

#### Scenario: Locked profile bypasses startup settings

- **GIVEN** saved startup settings exist
- **AND** `LOCKED_PROFILE = "mars_rover"`
- **WHEN** the app launches
- **THEN** the saved settings are not used
- **AND** the active profile is `mars_rover`

#### Scenario: Optional empty values normalize to None

- **GIVEN** `startup_settings.json` has an empty string voice value
- **WHEN** the settings are loaded
- **THEN** `_normalize_optional_text` returns `None` for the voice
- **AND** the backend's default voice is used

### Requirement: Hot-Apply Personality

When the user clicks Apply in the Gradio UI on a non-locked instance, the new personality's composed instructions SHALL be sent to the active session and the in-memory active profile reference SHALL update. The WebRTC stream MUST NOT be dropped.

#### Scenario: Applying a profile updates session instructions

- **GIVEN** a running session under `default`
- **WHEN** the user applies `noir_detective`
- **THEN** the session receives a new system prompt composed from `noir_detective/instructions.txt`
- **AND** the WebRTC audio stream stays open

#### Scenario: Applied voice persists across profile changes

- **GIVEN** the user has manually set voice `shimmer`
- **WHEN** they apply a different profile
- **THEN** `shimmer` remains the active voice
- **AND** the profile's `voice.txt`, if any, is not applied as an override

### Requirement: Creating a New Profile From the UI

The Gradio UI SHALL allow creating a new profile by submitting a name and an instructions body. On submit, the system MUST create `profiles/<name>/instructions.txt` and copy `profiles/default/tools.txt` into the new folder.

#### Scenario: New profile creation

- **GIVEN** the user enters name `kitchen_bot` and an instructions body in the UI
- **WHEN** they submit the creation form
- **THEN** `profiles/kitchen_bot/instructions.txt` is created with the submitted body
- **AND** `profiles/kitchen_bot/tools.txt` is copied from the default profile

#### Scenario: Name collision is rejected

- **GIVEN** a profile `mars_rover` already exists
- **WHEN** the user tries to create another `mars_rover`
- **THEN** the creation is rejected with a clear error
- **AND** the existing profile is untouched

### Requirement: Built-In Profile Catalogue

The wheel SHALL ship the following built-in profiles, each with at minimum an `instructions.txt` and a `tools.txt`:

`default`, `example`, `bored_teenager`, `captain_circuit`, `chess_coach`, `cosmic_kitchen`, `hype_bot`, `mad_scientist_assistant`, `mars_rover`, `nature_documentarian`, `noir_detective`, `sorry_bro`, `tedai`, `time_traveler`, `victorian_butler`.

#### Scenario: All shipped profiles load without error

- **GIVEN** a clean wheel install
- **WHEN** each shipped profile is loaded in turn
- **THEN** instruction composition succeeds for every profile
- **AND** every referenced tool resolves

### Requirement: Tool Set Is Loaded At Startup Only

Tool registration SHALL happen at app initialization time. Hot-applying a personality MUST NOT change the registered tool set for the live session. To change tools, the user must restart the app.

#### Scenario: Hot-apply preserves tool registry

- **GIVEN** the current session has the `default` profile's tools registered
- **WHEN** the user applies `mars_rover` (whose `tools.txt` differs)
- **THEN** the registered tools are unchanged for the live session
- **AND** the UI documents that a restart is needed for tool changes to take effect

## Implementation Anchors

| Concept | Source |
|---------|--------|
| Headless personality manager | `src/reachy_mini_conversation_app/headless_personality.py` (`available_tools_for`, `list_personalities`, `_profiles_root`, `_prompts_dir`) |
| Prompt composition | `src/reachy_mini_conversation_app/prompts.py` |
| Startup settings persistence | `src/reachy_mini_conversation_app/startup_settings.py` (`load_startup_settings_into_runtime`, `_normalize_optional_text`) |
| Locked profile constant | `src/reachy_mini_conversation_app/config.py` (`LOCKED_PROFILE`) |
| `apply_personality` on handlers | `base_realtime.py`, `huggingface_realtime.py`, `gemini_live.py` |
| Headless personality routes (FastAPI) | `src/reachy_mini_conversation_app/headless_personality_ui.py` (`mount_personality_routes`) |
| Gradio personality UI | `src/reachy_mini_conversation_app/gradio_personality.py` (`PersonalityUI`, `_parse_enabled_tools`) |
| External profile loading & fallback | `config.py`, `core_tools.py` (`_load_profile_tools`) |
| Packaged profile root | `setup.py` (`BuildPyWithProfiles` copies `profiles/` into `reachy_talk_data`) |
