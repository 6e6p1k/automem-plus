---
name: canary
description: Check whether built-in auto memory now covers what automem-plus adds (six short Haiku calls).
disable-model-invocation: true
---

The automem-plus hook normally answers this command itself, before it reaches you. You are reading this, so the hook did not run: the plugin's hooks are disabled, `AUTOMEM_DISABLE` is set, or this kind of session doesn't load plugin hooks.

Tell the user that in one sentence, and that `claude plugin list` shows whether automem-plus is enabled. Don't make up the command's answer.
