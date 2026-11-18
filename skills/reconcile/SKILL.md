---
name: reconcile
description: "Unite auto memory that was merged from several machines: duplicates, notes that disagree, copies that lost a conflict."
argument-hint: "[all]"
disable-model-invocation: true
---

Unite this project's auto memory, which was put together from more than one machine.

The automem-plus hook has added the instructions, the copies that lost a file conflict and the names of the notes that arrived. Follow them: propose first, and change nothing until the user agrees.

If no such instructions were added, the plugin's hooks didn't run. Say so and stop.
