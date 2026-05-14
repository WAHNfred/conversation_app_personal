# Reachy Mini Conversation App — Specification

This directory contains the OpenSpec-style behavioral specification of the Reachy Mini Conversation App. It is the **fachlicher Hintergrund** (functional baseline) used as the source of truth for downstream change proposals and AI-assisted code generation.

The specification was reverse-engineered from the current implementation (v0.6.2, commit `85ba8f8`). It captures *what the system does today*, not what it should do tomorrow. Future work is expressed as OpenSpec change proposals that delta against these specs.

## Conventions

This specification follows the [OpenSpec](https://github.com/Fission-AI/OpenSpec) format:

- Each capability is a single Markdown file under [`specs/`](specs/).
- Behavior is described as numbered **Requirements** (`### Requirement: ...`) using EARS-style **SHALL / MUST / SHOULD** verbs.
- Every requirement has at least one **Scenario** (`#### Scenario: ...`) with **GIVEN / WHEN / THEN** steps. Scenarios are the testable contract.
- Cross-references between capabilities use Markdown links.

## How to read it

1. Start with [`project.md`](project.md) — purpose, tech stack, architecture overview, conventions.
2. Then drill into a capability under [`specs/`](specs/).
3. To answer "where is X implemented?", consult the knowledge graph (`graphify-out/graph.json`) — it maps every concept here to source files and edges.

## Capabilities (Source of Truth)

| Capability | Description |
|------------|-------------|
| [conversation-and-backends](specs/conversation-and-backends.md) | Realtime voice loop, pluggable backends (Hugging Face / OpenAI / Gemini), session lifecycle. |
| [tool-system](specs/tool-system.md) | LLM-facing tool registry, function-calling dispatch, background tool execution, cancellation. |
| [motion-system](specs/motion-system.md) | Primary moves (dances, emotions, goto, breathing), secondary moves (speech-reactive wobble, head-tracking offsets), 100 Hz control loop. |
| [perception-system](specs/perception-system.md) | Camera worker, head-tracking backends (YOLO / MediaPipe), local VLM (SmolVLM2). |
| [personality-system](specs/personality-system.md) | Profiles, `instructions.txt`/`tools.txt`/`voice.txt`, prompt composition, locked profile mode, external profiles/tools. |
| [user-interfaces](specs/user-interfaces.md) | Console mode, Gradio Web UI, headless settings UI, FastAPI personality routes. |
| [configuration-and-runtime](specs/configuration-and-runtime.md) | `.env` handling, runtime config refresh, backend wiring, Hugging Face connection modes, startup settings persistence. |

## Maintaining the spec

- Treat specs as living documentation: when behavior changes, the spec changes in the same PR.
- For non-trivial changes, write an OpenSpec change proposal under `spec/changes/<change-id>/` with `proposal.md`, `tasks.md`, and deltas against the affected capability files.
- Keep scenarios concrete and observable. Replace "the system handles X gracefully" with a specific input → expected behavior pair.

## See also

- [`CLAUDE.md`](../CLAUDE.md) — operational guidance for Claude Code
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — code contribution workflow
- [`README.md`](../README.md) — end-user documentation
- [`graphify-out/GRAPH_REPORT.md`](../graphify-out/GRAPH_REPORT.md) — code-structure knowledge graph
