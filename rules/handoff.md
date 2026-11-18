# Handoff note (automem-plus)

Keep one auto-memory handoff note for the work in this session: the file `{handoff_file}` in your auto-memory folder (type `project`){branch_clause}. It lets the next session continue without the user explaining anything again. Other `handoff-*.md` notes belong to other branches and the sessions working on them; don't edit those.

Update it when the user says they're done for now ("done for today", "that's it for now", "stopping here"), after a push, and when the user runs the handoff command (`/automem-plus:handoff` or `::handoff`). Rewrite it in place; never start a second one. Keep its line in MEMORY.md.

If an older note already tracks where this same work stands (a "where we are", status or progress note, or a plain `handoff.md`), fold what's still true into `{handoff_file}` and delete the old note and its MEMORY.md line, so there's only one.

Sections, short bullets each:
- **Goal:** one line, what we're building right now
- **Where we are:** what works, what doesn't, branch and last commit
- **Tried and failed:** dead ends from this stretch and why, so nobody repeats them
- **Open decisions:** questions still undecided
- **Next steps:** ordered; the first one is where the next session starts

Only state that goes out of date belongs here. Lasting facts (decisions that held, preferences, pitfalls) go in their own memory notes as usual. Once this branch is merged, move anything lasting into its own note and delete the handoff.

At the start of a session, if the user's first message is about continuing work, read `{handoff_file}` before answering, and check it against `git log` since it was written.
