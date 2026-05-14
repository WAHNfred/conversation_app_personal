# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hardware target (verbindlich)

> **Der Besitzer dieses Repos arbeitet ausschließlich mit Reachy Mini in der WIRELESS-Variante.**

Jeder Vorschlag, Patch, Befehl, Dependency-Pick und jede Spec-Änderung MUSS diesen Hardware-Kontext berücksichtigen. Konkret heißt das:

- **Zielplattform** ist der eingebaute Raspberry Pi (SBC) der Wireless-Variante, plus optional ein per WLAN angebundener Laptop für Backend-Last (z. B. lokaler Hugging-Face-Server, lokales Vision-Modell).
- **`--local-vision` läuft NICHT auf dem Robot selbst.** Wenn lokale Vision gewünscht wird, läuft der Reachy-Daemon auf dem Robot und die Conversation App auf einem WLAN-Laptop. Die Spec-Anforderung "Restricted Platforms for Local Vision" in [`spec/specs/perception-system.md`](spec/specs/perception-system.md) gilt direkt.
- **GStreamer / `gi`** ist auf dem Wireless-Image vorhanden → der Default-Media-Backend funktioniert. Die Fallback-Kette `sounddevice_opencv` → `sounddevice_no_video` aus Commit `e36cded` ist defensiver Code für **andere** Setups (Reachy Lite, Laptops) und sollte für Wireless-spezifische Tests nicht als primärer Codepfad behandelt werden.
- **Mikrofon** ist die XVF3800-Onboard-Mikrofonzeile; `apply_audio_startup_config` MUSS einmalig beim Boot laufen.
- **Kamera ist eingebaut.** `--no-camera` ist nicht der Default-Modus, es sei denn explizit angefordert.
- **Bevorzugte Backend-Konfigurationen** (in Reihenfolge):
  1. `BACKEND_PROVIDER=huggingface` + `HF_REALTIME_CONNECTION_MODE=deployed` — out-of-the-box, ohne API-Key.
  2. `BACKEND_PROVIDER=huggingface` + `HF_REALTIME_CONNECTION_MODE=local` mit `HF_REALTIME_WS_URL=ws://<lan-laptop>:8765/v1/realtime` — wenn man die HF-Pipeline lokal kontrollieren will.
  3. OpenAI / Gemini — wenn die API-Keys vorhanden sind und Cloud-Latenz akzeptabel ist.
- **Schwergewichtige Local-Inferenz-Dependencies** (PyTorch, Transformers, SmolVLM2) NICHT zum Wireless-Image hinzufügen. Die Wireless-Plattform ist ressourcenbegrenzt.

Wenn ein Vorschlag oder Patch nur für eine andere Hardware (Reachy Lite, simulierter Robot, Desktop ohne Robot) sinnvoll ist, kennzeichne das explizit in Plan und Commit-Message.

## Git workflow (verbindlich)

Dieses Repo ist ein **Fork** von `pollen-robotics/reachy_mini_conversation_app`. Eigene Anpassungen leben auf `personal` (oder Feature-Branches davon) in `WAHNfred/conversation_app_personal`; der `main`-Branch ist sauberer Spiegel von `upstream/main`.

Vollständiger Workflow in [`git-Befehle.md`](git-Befehle.md). Kurzform:

- **`upstream`** = `pollen-robotics/...` (nur fetch, niemals push)
- **`origin`** = `WAHNfred/conversation_app_personal` (eigener Fork)
- **`main`** trackt `upstream/main`, wird NIE direkt beschrieben — nur via `git merge upstream/main`
- **`personal`** ist der Default-Arbeitsbranch; alle eigenen Commits landen hier
- **`git push --force` ist tabu**, `--force-with-lease` nur nach expliziter Bestätigung
- **Nach `upstream` wird niemals gepusht**

Bei Code-Änderungen in einer Session:

1. Vor jedem Commit `git status --short` und `git log --oneline -5` zeigen.
2. Niemals auf `main` committen — vor einem Commit prüfen: `git rev-parse --abbrev-ref HEAD` MUSS `personal` (oder ein davon abgeleiteter Branch) sein.
3. Bei "hol Upstream rein"-Aufträgen den Workflow aus [`git-Befehle.md`](git-Befehle.md) Abschnitt B ausführen und Konflikte zur Auflösung vorlegen, nicht stillschweigend bearbeiten.

## Knowledge graph first

Before exploring the codebase with Glob/Grep/Read for structural questions ("where is X defined", "what calls Y", "how does Z connect to W", "what are the main modules"), **consult the knowledge graph at `graphify-out/graph.json` first**. It contains 1368 nodes and 2093 edges covering all code, docs, profiles, and assets, clustered into named communities (Realtime Audio Backend Core, MovementManager, Tool System, etc.) with cross-community bridges already identified.

Useful entry points:
- `graphify-out/GRAPH_REPORT.md` — god nodes, surprising connections, community labels
- `graphify-out/graph.html` — interactive visualization
- `/graphify query "<question>"` — BFS traversal answering a question from the graph
- `/graphify path "A" "B"` — shortest path between two concepts
- `/graphify explain "NodeName"` — explain a node and its connections

After any non-trivial code change, run `/graphify <path> --update` to keep the graph in sync.

## Specification is the source of truth

The behavioral specification under [`spec/`](spec/) is the **fachlicher Hintergrund** (functional baseline) for this codebase. It is structured in OpenSpec format with `### Requirement` (EARS-style SHALL/MUST/SHOULD) and `#### Scenario` (GIVEN/WHEN/THEN) sections across seven capability files:

- [`spec/specs/conversation-and-backends.md`](spec/specs/conversation-and-backends.md) — realtime loop, OpenAI / Gemini / Hugging Face backends
- [`spec/specs/tool-system.md`](spec/specs/tool-system.md) — tool registry, function-call dispatch, background tasks
- [`spec/specs/motion-system.md`](spec/specs/motion-system.md) — primary/secondary blend, dances, emotions, wobbler
- [`spec/specs/perception-system.md`](spec/specs/perception-system.md) — camera, head trackers, local vision
- [`spec/specs/personality-system.md`](spec/specs/personality-system.md) — profiles, prompts, locked mode
- [`spec/specs/user-interfaces.md`](spec/specs/user-interfaces.md) — console, Gradio, headless settings
- [`spec/specs/configuration-and-runtime.md`](spec/specs/configuration-and-runtime.md) — `.env`, CLI flags, resolution chain

### Domain glossary (canonical vocabulary)

The shared domain language for this codebase lives in [`spec/CONTEXT.md`](spec/CONTEXT.md). It is the single source of truth for term definitions and follows the Matt Pocock `grill-with-docs` `CONTEXT.md` format, so it works directly with that skill (and with any agent that scans for `CONTEXT.md` in the repo).

Use it for three things:

1. **Read it before drafting any Requirement, Scenario, plan, commit message, or PR description** — every domain term you write should match an entry in `CONTEXT.md` verbatim (casing included).
2. **Challenge fuzzy language during planning** — if the user or another agent uses a term that conflicts with `CONTEXT.md` ("backend" without qualifier, "vision" without mode, "headless" alone, etc.), call it out, quote the canonical definition, and ask which precise meaning is intended. The `Flagged ambiguities` section enumerates the known overloaded terms.
3. **Keep the glossary current** — when a new domain concept is introduced (not just a new feature), add it to `CONTEXT.md` in the same PR with: a one-sentence definition, an `_Avoid_` list of synonyms to retire, and an update to `Relationships` if it touches other concepts. If two specs disagree on a term, the glossary wins — update the spec to match, not the other way around.

When invoking `grill-with-docs` or any planning-style skill in this repo, point it at `spec/CONTEXT.md` rather than letting it create a fresh `CONTEXT.md` at the root.

**Whenever a new feature, change request, or bug report is described**, the description MUST be checked against this specification before any planning or implementation:

1. **Find the affected capability file(s)** by topic or by the Implementation Anchors table at the bottom of each spec.
2. **Locate the relevant Requirements and Scenarios** that touch the same area.
3. **Check for contradictions**: does the new behavior violate an existing Requirement? If yes, name the conflicting Requirement explicitly and ask the user how to resolve it (modify the spec, scope the change differently, or reject).
4. **Check for ambiguity**: is the new description compatible with the spec but underspecified — e.g. silent on an edge case the spec already covers, or using a term the spec defines differently? If yes, surface the ambiguity with a concrete question before proceeding.
5. **Only then plan or implement.** When the change lands, update the affected Requirement / Scenario in the same PR so the spec stays the source of truth.

Do NOT silently reinterpret the user's request to fit the spec, and do NOT silently ignore the spec to satisfy the request. Flag the conflict, then ask.

### Checking and aligning new requirements

Whenever a new requirement is drafted — whether as a user story, a change-proposal entry, a bug-fix acceptance criterion, or a new `### Requirement` to be added to the spec — it MUST be cross-checked against the existing specification along four axes before it is accepted:

1. **Gaps (Lücken)** — Does the new requirement cover behavior the spec is currently silent on? If yes, that gap is exactly what the new requirement should fill. Name the gap explicitly: which capability file is currently silent and on which Scenario boundary.
2. **Overlaps (Überlappungen)** — Does the new requirement re-state behavior an existing Requirement already mandates? If yes, do NOT duplicate. Either reference the existing Requirement, extend it with an additional Scenario, or amend it via an OpenSpec MODIFIED delta.
3. **Contradictions (Widersprüche)** — Does the new requirement assert something that violates an existing Requirement? If yes, name the conflicting Requirement(s) explicitly and ask whether to (a) reject the new requirement, (b) MODIFY the existing one, or (c) REMOVE the existing one and replace.
4. **Inconsistencies (Inkonsistenzen)** — Does the new requirement use different verbs, edge-case handling, or precondition semantics than the spec uses for comparable behavior? If yes, harmonize before accepting.

#### Wording alignment

After the four-axis check, rewrite the new requirement to match the spec's vocabulary so the entire body of requirements speaks one language. Specifically:

- **Use the spec's EARS verbs** — `SHALL` for mandatory behavior, `MUST` for invariants, `SHOULD` for strong recommendations, `MAY` for permitted options. Do not introduce new modal verbs.
- **Reuse the spec's domain nouns verbatim** — e.g. `realtime backend`, `primary move` / `secondary offset`, `ToolDependencies`, `BackgroundToolManager`, `LocalStream`, `connection mode (deployed / local)`, `locked profile mode`, `instance .env`, `startup settings`. If you find yourself wanting a synonym, the spec's term wins. If the spec's term is genuinely wrong, fix the spec first in a separate proposal.
- **Reuse Scenario phrasing patterns** — `GIVEN <stable precondition> · WHEN <single triggering action> · THEN <one observable outcome>`. Avoid stacking multiple WHENs or hiding multiple outcomes inside one THEN.
- **Reuse capability boundaries** — if the behavior belongs in `motion-system`, do not introduce its requirement under `tool-system`. Cross-capability behavior is expressed as a reference link between Requirements, not as duplication.
- **Reuse identifier casing** — class names PascalCase (`MovementManager`), tool names snake_case as exposed to the LLM (`move_head`), env variables UPPER_SNAKE (`HF_REALTIME_CONNECTION_MODE`), file paths in backticks relative to repo root.

If a new requirement cannot be expressed in the spec's vocabulary without losing meaning, that is itself a signal that the spec is missing a concept — propose adding the concept (with a definition) in the same change.

## Commands

```bash
# Setup
uv venv --python python3.12 .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
uv sync

# Run app
reachy-mini-conversation-app

# Lint & format
uv run ruff check . --fix
uv run ruff format .

# Type check
uv run mypy --pretty --show-error-codes

# Tests
uv run pytest tests/ -v
uv run pytest tests/test_config.py -v   # single file
uv run pytest -k "test_name" -v         # single test

# All checks
uv run ruff check . --fix && uv run ruff format . && uv run mypy --pretty --show-error-codes && uv run pytest tests/ -v
```

Optional extras for vision features: `uv sync --extra local_vision`, `--extra yolo_vision`, `--extra mediapipe_vision`.

## Architecture

This is a real-time voice conversation app for the Reachy Mini humanoid robot. Three main layers:

### 1. Realtime Audio Backend (pluggable)
`conversation_handler.py` defines the `ConversationHandler` ABC. Three concrete implementations:
- `HuggingFaceRealtimeHandler` — default backend
- `OpenAIRealtimeHandler` / `GeminiLiveHandler` — extend `BaseRealtimeHandler` (`base_realtime.py`)

All backends use `fastrtc` for low-latency audio streaming.

### 2. Tool System
`tools/core_tools.py` defines the `Tool` base class and `ToolDependencies`. Tools are loaded per-personality from `profiles/<name>/tools.txt`. Custom tool Python files can live in the profile directory.

`BackgroundToolManager` (`tools/background_tool_manager.py`) handles async tool execution and status tracking during conversations.

### 3. Robot Motion (`moves.py`)
`MovementManager` runs a ~60 Hz control loop on a dedicated worker thread. It blends:
- **Primary moves** — mutually exclusive (dances, emotions, goto poses, breathing)
- **Secondary moves** — additive (speech-reactive head wobble, head-tracking offsets)

### Vision (`camera_worker.py`, `vision/`)
Optional `CameraWorker` thread captures frames and feeds head-tracking backends (YOLO or MediaPipe). Local VLM inference via SmolVLM2 is a separate optional extra.

### Personality / Profile System
Profiles live in `profiles/<name>/` with `instructions.txt`, `tools.txt`, and optional `voice.txt`. External profiles can be mounted via env vars. `config.py` loads all runtime configuration from `.env` via `python-dotenv`.

### UI
- Console mode (default): `console.py`
- Web UI: Gradio at `http://127.0.0.1:7860/` (`--gradio` flag), implemented in `gradio_personality.py`

## Key Conventions

- **AI-generated code** must be reviewed by a human, kept minimal, and not bulk-modified — see CONTRIBUTING.md.
- Commits follow conventional commits style; PRs target `main` with one feature/fix per branch.
- Tests: regression tests for every bug fix; happy-path tests for new features.
- Ruff `ruff.toml` and mypy are both enforced in CI — run both locally before pushing.
