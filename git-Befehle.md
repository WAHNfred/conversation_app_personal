# Git-Workflow für dieses Repo (Fork-Setup)

Dieses Dokument ist die **verbindliche Git-Arbeitsweise** für dieses Projekt. Jede Claude-Code-Session in diesem Repo arbeitet nach diesem Schema. Es wird aus [`CLAUDE.md`](CLAUDE.md) heraus referenziert.

## Grundprinzip

Das Repo ist ein **Fork** von `pollen-robotics/reachy_mini_conversation_app`. Eigene Anpassungen leben auf einem Personal-Branch in einem **privaten Fork** (`WAHNfred/conversation_app_personal`); der `main`-Branch bleibt sauberer Spiegel des Upstream.

```
pollen-robotics/reachy_mini_conversation_app   ← upstream (read-only)
        │ git fetch
        ▼
local: main                                    ← spiegelt upstream/main 1:1
        │ git merge
        ▼
local: personal                                ← hier passiert alle eigene Arbeit
        │ git push
        ▼
WAHNfred/conversation_app_personal             ← origin (eigener Fork)
```

## Remote-Konvention

| Remote | URL | Verwendung |
|--------|-----|------------|
| `upstream` | `https://github.com/pollen-robotics/reachy_mini_conversation_app` | nur `fetch` (lesend) — niemals push |
| `origin` | `https://github.com/WAHNfred/conversation_app_personal` | `push` der eigenen Arbeit |

## Branch-Konvention

| Branch | Tracking | Inhalt |
|--------|----------|--------|
| `main` | `upstream/main` | **niemals selbst committen**; nur via `git merge upstream/main` aktualisiert. Wird auch nach `origin/main` gepusht, damit der Fork-Spiegel mitläuft. |
| `personal` | `origin/personal` | alle eigenen Commits leben hier |
| `feat/...`, `fix/...` | `origin/<branch>` | optional: Feature-Branches abgeleitet von `personal` |

## Einmalsetup (bereits durchgeführt)

```powershell
# 1. Bestehendes origin (zeigte auf upstream) umbenennen
git remote rename origin upstream

# 2. Fork als neues origin eintragen
git remote add origin https://github.com/WAHNfred/conversation_app_personal.git

# 3. main von Upstream tracken lassen
git branch --set-upstream-to=upstream/main main

# 4. Personal-Branch anlegen mit den eigenen Commits
git branch personal
git push -u origin personal

# 5. main zurück auf Upstream-Stand und auf Fork spiegeln
git checkout main
git reset --hard upstream/main
git push -u origin main
```

## Tagesgeschäft

### A. Eigene Arbeit committen

```powershell
git checkout personal
# ... Code/Doku ändern ...
git add .
git commit -m "feat: ..."
git push                # → origin/personal
```

### B. Upstream-Änderungen holen und in eigene Arbeit integrieren

```powershell
# 1. Aktuellen Upstream-Stand holen
git fetch upstream

# 2. Lokales main auf Upstream nachziehen (fast-forward only — niemals committen auf main)
git checkout main
git merge --ff-only upstream/main
git push origin main    # Fork-Spiegel mitziehen

# 3. Upstream-Änderungen in personal mergen
git checkout personal
git merge main
# Konflikte? — bearbeiten, dann:
#   git add <datei>
#   git commit
git push                # → origin/personal
```

### C. Saubere Linie statt Merge (optional, fortgeschritten)

Wenn die Personal-Historie linear bleiben soll und niemand sonst den Branch klont:

```powershell
git checkout personal
git rebase main
git push --force-with-lease    # NIE plain --force, immer --force-with-lease
```

Vorteile: keine Merge-Commits, deine Arbeit liegt immer "oben drauf" auf `upstream/main`.
Nachteile: schreibt Historie um, kann den Branch für andere Klone unbrauchbar machen.

## Was Claude für dich machen soll

Bei eigenen Code-Änderungen in dieser Session:

- **Immer auf `personal` (oder Feature-Branch davon)**, niemals auf `main` committen.
- Vor dem `push` auf `origin` immer das aktuelle `git status --short` und `git log --oneline -5` zeigen, damit du sehen kannst, was rausgeht.
- Wenn du sagst "hol mal Upstream rein", führt Claude Workflow **B** durch und meldet zurück, ob Konflikte aufgetreten sind.
- Bei Konflikten **nicht** automatisch lösen — Konflikte zuerst zeigen, gemeinsam entscheiden.
- `git push --force` ist tabu. `--force-with-lease` nur nach expliziter Bestätigung.
- Niemals nach `upstream` pushen.

## Konfliktauflösung — Cheatsheet

```powershell
# Konflikte anzeigen
git status

# Datei im Editor öffnen, Markierungen <<<<<<<, =======, >>>>>>> auflösen
# Dann:
git add <gelöste-datei>
git commit                 # nur wenn Merge-Konflikt
# oder:
git rebase --continue      # nur wenn Rebase-Konflikt

# Abbrechen, falls etwas schiefging:
git merge --abort
git rebase --abort
```

## Reines Lesen ohne lokale Auswirkung

```powershell
# Was hat sich auf upstream getan?
git fetch upstream
git log --oneline main..upstream/main      # Commits in upstream, die ich noch nicht habe

# Welche Dateien wären betroffen?
git diff --stat main upstream/main

# Was hab ich gegenüber upstream geändert?
git log --oneline upstream/main..personal
git diff --stat upstream/main personal
```

## Wichtig: niemals nach upstream pushen

`upstream` ist **read-only**. Selbst wenn du theoretisch Push-Rechte hättest, gehen eigene Anpassungen IMMER auf `origin` (= dein Fork). Pull Requests an upstream werden bewusst über die GitHub-Web-UI gestellt (vom Personal-Branch des Forks aus), nicht direkt gepusht.
