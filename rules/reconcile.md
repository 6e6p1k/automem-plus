# Reconcile memory (automem-plus)

The user ran `::automem reconcile`. This project's auto memory was put together from more than one machine, file by file, so notes can overlap or disagree. Unite it in two steps: propose, then apply once the user agrees.

Memory folder: `{folder}`

{conflicts}

{arrived}

Read every note in the folder. The copies that lost are quoted above, so you don't need to open them. Then look for:

- **The same thing in two notes,** often under different file names, one from each machine. Merge them into one note and keep every fact that still holds.
- **A copy that lost a file conflict** (listed above). Compare it with the note that was kept, and carry over anything true that the kept note lacks.
- **Notes that disagree.** Which one is newer doesn't settle it:
  - About where the work stands (what's done, what's next): the repo decides. Check `git log` and the code, keep what matches, and put it in `{handoff_file}` instead of a separate status note. Handoffs of other branches stay as they are.
  - About something the user wants or how they want you to work: show both versions and ask.
  - About a fact (a path, a command, a tool): check it if you can, otherwise ask.
- **MEMORY.md lines that describe the copy that lost** or point at a note that's gone.

Leave a note alone when it overlaps with nothing. Don't reword, shorten or restructure notes for their own sake.

First show the user a short list: for each change, the notes involved, what you'd do (merge into which note, delete which, ask what) and one line on why. Put your questions in the same message. Change nothing until they answer.

Then apply it: edit the notes you keep, delete the ones merged away, and give MEMORY.md one line per note. Don't edit or delete the saved copies outside the memory folder. Finish with one line on what changed. The result reaches the user's other machines at the next sync, and every earlier version stays in the store's git history.
