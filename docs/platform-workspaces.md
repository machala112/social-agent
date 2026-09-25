# Platform workspaces

Every social platform gets its own source tree: `platforms/<platform>/`.
The design is generic — ANY platform (not just the seven we ship recipes
for) gets one via `social-agent workspace init --platform <name>`
(linkedin was added this way as the 7th platform).

## The tree

```
platforms/<name>/
  __init__.py        adapter spec (declarative: watchers, ToS, memory view)
  terms.md / tos_rules.yaml
  watchers/          REGISTRATION manifest (which watchers + defaults)
  memory/            namespaced VIEW into the shared DB (no .db copy)
  workspace/         shipped workspace template
```

## The two rules

1. **Platform trees hold declarations, not execution.** Execution
   happens in the agent's own browser via hands tickets
   (`hands/HANDS.md`) — the tree only declares the adapter spec, the
   ToS rules, watcher registrations, and a memory view.
2. **Platform trees NEVER duplicate shared core.** Memory, the watcher
   scheduler, the event bus, the video editor, audio engine, caption
   generator, analytics DB, and the human approval system exist exactly
   once (see `core/SHARED_CORE.md`). `tests/test_shared_core.py` fails
   the build if a shared-core module shows up under `platforms/`.

## Watcher lifecycle per platform

Platforms never implement watchers — they register them:

```python
from core.watcher_engine import WatcherEngine
from platforms.tiktok import watchers as tw

engine = WatcherEngine(home)            # shared engine, single instance
tw.register(engine, account="main")     # 14 watchers: tiktok:notification, ...
```

Registering the same platform twice is refused
(`DuplicateWatcherError`) — a watcher id is registered exactly once.

## What lives in a workspace

- `workspace.yaml` — platform name, identity + account labels, notes.
- `state/` — platform-specific runtime state. Survives restarts;
  covered by backups.
- `notes.md` — human-editable per-platform playbook notes (optional).

Watcher checkpoints (cursors) live in the shared memory DB
(`watcher_checkpoints` table), not in `state/` — a fresh VM resumes
watchers from memory without replaying or missing events. The JSON
sidecar under `<home>/watchers/<id>.json` is a legacy mirror only.

## What NEVER lives in a platform tree

Copies of shared-core modules, browser profile data, credentials, API
keys (there are no APIs — hands tickets only), or cache files.
