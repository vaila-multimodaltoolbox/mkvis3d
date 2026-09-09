# Agent Guidance

This repository uses a git-backed, harness-independent memory protocol.

Before substantive work in every new task or session:

1. Read `.ai-memory/PROTOCOL.md`.
2. Read `.ai-memory/HANDOFF.md` and `.ai-memory/FACTS.md`.
3. Also inspect root `MEMORIES.md` or `HANDOFF.md` if either exists.
4. Read `CLAUDE.md` for the current project phase, commands, and engineering
   conventions.

Follow `.ai-memory/PROTOCOL.md` throughout the task. In particular, update the
handoff when work completes or the session ends, obtain user approval before
recording a newly discovered durable project fact, never use placeholder or
truncated implementations, and provide reproducible verification.
