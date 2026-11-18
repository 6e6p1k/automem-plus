---
name: handoff
description: Update this session's handoff note now, so the next session can continue.
disable-model-invocation: true
---

Update the handoff note for this session now.

The automem-plus hook has added which file that is. Follow the handoff rule from the start of the session (Goal, Where we are, Tried and failed, Open decisions, Next steps), keep the note's `MEMORY.md` line, then confirm in one short line.

If no added context names the file, the plugin's hooks didn't run. Say so, and write the note as `handoff-<branch>.md` in your auto-memory folder (`handoff.md` outside a git repo).
