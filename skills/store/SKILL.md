---
name: store
description: "Set up the git repo that carries auto-memory notes between machines."
argument-hint: "<git-url>|init"
disable-model-invocation: true
---

The automem-plus hook normally answers this command itself, before it reaches you. You are reading this, so the hook did not run: the plugin's hooks are disabled, `AUTOMEM_DISABLE` is set, or this kind of session doesn't load plugin hooks.

Tell the user that in one sentence, and that `claude plugin list` shows whether automem-plus is enabled. Don't make up the command's answer.
