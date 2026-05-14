# Spec: Tool System

## Purpose

Defines how the LLM-facing tool registry, function-calling dispatch, and background tool execution work. This capability owns:

- The `Tool` base class and `ToolDependencies` aggregate.
- Tool discovery, name-collision protection, and per-profile tool filtering.
- The seven built-in tools (`move_head`, `camera`, `head_tracking`, `dance`, `stop_dance`, `play_emotion`, `stop_emotion`, `idle_do_nothing`) and the two task-management tools (`task_status`, `task_cancel`).
- `BackgroundToolManager`: non-blocking execution, progress tracking, cancellation, and `ToolNotification` delivery back to the conversation.
- External-tool loading (`REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`) and the autoload escape hatch (`AUTOLOAD_EXTERNAL_TOOLS=1`).

This capability is consumed by [conversation-and-backends](conversation-and-backends.md), which calls into the registry to build session tool specs and to dispatch function calls.

## Requirements

### Requirement: Tool Contract

Every tool SHALL subclass `reachy_mini_conversation_app.tools.core_tools.Tool` and provide:

- A classmethod returning an OpenAI-compatible function spec (`name`, `description`, `parameters` JSON schema).
- An `async run(tool_dependencies, ...)` method that performs the action and returns a JSON-serializable result string or dict.
- A declaration of which `ToolDependencies` fields it requires, so it can be filtered out when those dependencies are unavailable.

#### Scenario: Tool exposes a function spec

- **GIVEN** the `Dance` tool class
- **WHEN** `Dance.function_spec()` is invoked
- **THEN** it returns a dict with `name="dance"`, a human-readable `description`, and a `parameters` schema describing the `dance_name` and optional `repeat` arguments

#### Scenario: Tool execution returns serializable result

- **GIVEN** a tool that captures a camera frame
- **WHEN** the tool's `run` method completes successfully
- **THEN** the return value is JSON-serializable and is delivered back to the LLM as the function-call result

### Requirement: Tool Dependencies Filtering

The system SHALL filter the active tool set at session-open time based on which `ToolDependencies` are present. A tool whose required dependency is missing MUST NOT appear in the session's tool spec.

#### Scenario: Camera tool hidden when camera worker disabled

- **GIVEN** the app is started with `--no-camera`
- **WHEN** `get_active_tool_specs()` is called
- **THEN** the `camera` tool is excluded from the result
- **AND** the `head_tracking` tool is also excluded (it depends on the camera worker)

#### Scenario: Head-tracking tool hidden when no tracker backend selected

- **GIVEN** the app is started without `--head-tracker`
- **WHEN** the session is built
- **THEN** the `head_tracking` tool is excluded even if the camera worker is otherwise active

### Requirement: Profile-Driven Tool Allowlist

Each profile's `tools.txt` SHALL define the set of tools allowed for that profile. Tool resolution order MUST be: (1) Python files in the profile folder, (2) external tools under `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`, (3) built-in tools under `src/reachy_mini_conversation_app/tools/`.

#### Scenario: Comment lines are ignored

- **GIVEN** a `tools.txt` containing `play_emotion`, a blank line, and `# move_head`
- **WHEN** the profile is loaded
- **THEN** `play_emotion` is enabled
- **AND** `move_head` is treated as commented-out and not enabled

#### Scenario: Profile-local tool overrides built-in with same name

- **GIVEN** profile `example` contains a Python file `dance.py` defining a custom `Dance` tool class
- **WHEN** the profile is loaded
- **THEN** the profile-local `Dance` is registered, shadowing the built-in `dance` tool

#### Scenario: Missing tool name fails fast

- **GIVEN** a `tools.txt` referencing `nonexistent_tool`
- **WHEN** the profile is loaded in strict mode
- **THEN** startup fails with a clear error naming the missing tool

#### Scenario: External profile falls back to default tools.txt

- **GIVEN** an external profile with no `tools.txt`
- **WHEN** the profile is loaded
- **THEN** the built-in `profiles/default/tools.txt` is used as fallback

### Requirement: Name Collision Protection

The configuration loader SHALL refuse to start when an external tool module and a built-in tool module share the same name, or when an external profile and a compact built-in profile name share the same name.

#### Scenario: External tool collides with built-in name

- **GIVEN** `external_content/external_tools/dance.py` exists
- **AND** `dance` is also a built-in tool
- **WHEN** the app starts
- **THEN** `_raise_on_name_collisions` raises an error naming both paths
- **AND** the app does not start

#### Scenario: External profile collides with built-in compact name

- **GIVEN** `external_profiles/default/` exists alongside the built-in `default` profile
- **WHEN** the app starts
- **THEN** startup fails with a name-collision error

### Requirement: External-Tool Autoload Mode

When `AUTOLOAD_EXTERNAL_TOOLS=1` is set, every `*.py` file under `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` SHALL be loaded automatically, in addition to any explicitly listed in `tools.txt`. The strict-mode `tools.txt` requirement MUST still hold for built-in profiles using external tools.

#### Scenario: Autoload mode picks up unlisted external tools

- **GIVEN** `AUTOLOAD_EXTERNAL_TOOLS=1`
- **AND** `external_content/external_tools/my_extra.py` exists
- **WHEN** the app starts with the built-in `default` profile
- **THEN** `my_extra` is registered even though `default/tools.txt` does not list it

#### Scenario: External profile can use built-in tools

- **GIVEN** an external profile listing `dance` and `play_emotion` in `tools.txt`
- **WHEN** the app starts pointing at that external profile
- **THEN** both built-in tools are available to the LLM

### Requirement: Asynchronous Tool Dispatch

When the realtime backend issues a function call, the dispatcher SHALL run the tool asynchronously and return its result via the same function-call ID, never blocking the audio pipeline.

#### Scenario: Function call is routed by name

- **GIVEN** the LLM emits a function call `{"name": "move_head", "arguments": "{\"direction\": \"left\"}"}`
- **WHEN** `_dispatch_tool_call` runs
- **THEN** the registered `MoveHead` tool's `run` method is invoked with the parsed arguments

#### Scenario: Unknown tool name returns structured error

- **GIVEN** the LLM emits a function call for a name not in the active registry
- **WHEN** dispatch runs
- **THEN** an error JSON is returned to the LLM identifying the unknown tool
- **AND** the session continues without crashing

#### Scenario: Argument parse failure returns structured error

- **GIVEN** the LLM emits malformed JSON arguments
- **WHEN** dispatch runs
- **THEN** an error JSON describing the parse failure is returned
- **AND** no tool side-effects occur

### Requirement: Background Tool Manager

Tools that may take more than one turn to complete SHALL be runnable as background tasks managed by `BackgroundToolManager`. The manager MUST track lifecycle, expose progress, support cancellation, and emit a single `ToolNotification` per completed tool.

#### Scenario: Background tool runs without blocking the next turn

- **GIVEN** a long-running tool is dispatched as background
- **WHEN** the user starts a new turn before the tool completes
- **THEN** the conversation proceeds with the new turn
- **AND** the background tool continues running

#### Scenario: Completed background tool emits exactly one notification

- **GIVEN** a background tool runs to completion
- **WHEN** the manager observes the completion
- **THEN** exactly one `ToolNotification` is enqueued to the listener
- **AND** subsequent listener polls do not re-deliver the notification

#### Scenario: Cancellation stops a running tool

- **GIVEN** a running background tool with ID `xyz`
- **WHEN** the `task_cancel` tool is invoked with `tool_id=xyz`
- **THEN** the running task is cancelled
- **AND** the tool record is marked cancelled

#### Scenario: Cancelling an already-completed tool is a no-op

- **GIVEN** a background tool that already completed
- **WHEN** `task_cancel` is invoked with that tool's ID
- **THEN** cancellation succeeds (idempotent) and no exception is raised

#### Scenario: Cleanup removes old completed tools but keeps recent ones

- **GIVEN** the cleanup job runs periodically
- **WHEN** a completed tool record is older than the retention window
- **THEN** it is removed from the manager's history
- **AND** completed tools within the window remain queryable via `task_status`

#### Scenario: Cleanup ignores running tools

- **GIVEN** a tool that has been running longer than the cleanup retention window
- **WHEN** cleanup runs
- **THEN** the running tool is left untouched

### Requirement: Tool Progress Bounds

For tools that opt into progress reporting (`with_progress=True`), reported progress values MUST be in the closed interval `[0.0, 1.0]`. Out-of-range values SHALL be rejected.

#### Scenario: Boundary values are accepted

- **GIVEN** a tool with progress reporting enabled
- **WHEN** the tool reports progress `0.0` or `1.0`
- **THEN** both values are accepted and propagated to `ToolNotification`

#### Scenario: Out-of-range progress is rejected

- **GIVEN** a tool with progress reporting enabled
- **WHEN** the tool tries to report progress `1.5` or `-0.1`
- **THEN** `ToolProgress` rejects the value with a validation error

### Requirement: Task Status and Cancellation Tools

The system SHALL expose two LLM-callable tools `task_status` and `task_cancel` so the assistant can query and stop its own background tasks.

#### Scenario: task_status returns the list of background tools

- **GIVEN** two background tools running and one completed
- **WHEN** the LLM invokes `task_status`
- **THEN** the response includes all three records with their state (running / completed / cancelled), start time, and optional progress

#### Scenario: task_cancel cancels by ID

- **GIVEN** a background tool with a known ID
- **WHEN** the LLM invokes `task_cancel` with that ID
- **THEN** the targeted task is cancelled and the response acknowledges the cancellation

### Requirement: Idle Tool Behavior

The system SHALL expose an `idle_do_nothing` tool the LLM can call to explicitly stay silent during an idle turn. This tool MUST NOT cause any robot motion or speech.

#### Scenario: idle_do_nothing is callable and has no side effects

- **GIVEN** an idle turn opportunity
- **WHEN** the LLM invokes `idle_do_nothing`
- **THEN** the tool returns successfully with no motion, no audio, and no transcript message

## Implementation Anchors

| Concept | Source |
|---------|--------|
| `Tool` base class | `src/reachy_mini_conversation_app/tools/core_tools.py` |
| `ToolDependencies` aggregate | `src/reachy_mini_conversation_app/tools/core_tools.py` |
| Tool registry + filtering | `core_tools.py` (`_initialize_tools`, `get_tool_specs`, `get_active_tool_specs`) |
| Dispatch | `tools/background_tool_manager.py` (`_dispatch_tool_call`, `dispatch_tool_call_with_manager`) |
| Background manager | `tools/background_tool_manager.py` (`BackgroundToolManager`, `BackgroundTool`, `ToolNotification`, `ToolProgress`) |
| Built-in tools | `tools/dance.py`, `tools/play_emotion.py`, `tools/move_head.py`, `tools/camera.py`, `tools/head_tracking.py`, `tools/idle_do_nothing.py`, `tools/stop_dance.py`, `tools/stop_emotion.py`, `tools/task_status.py`, `tools/task_cancel.py` |
| External tool loading | `core_tools.py` (`_load_profile_tools`, `_load_module_from_file`, `MissingToolFileError`) |
| Name collision check | `config.py` (`_collect_profile_names`, `_collect_tool_module_names`, `_raise_on_name_collisions`) |
