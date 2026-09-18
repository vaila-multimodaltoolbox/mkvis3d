# Permanent Memory Protocol

This directory is the repository's shared, git-backed memory. It is plain
Markdown so Cursor, Claude Code, Codex, terminal agents, and human contributors
can resume work from the same evidence.

## Start of every task or session

Before substantive work:

1. Check `.ai-memory/`, root `MEMORIES.md`, and root `HANDOFF.md`.
2. Read `.ai-memory/HANDOFF.md` and `.ai-memory/FACTS.md` when present.
3. Ingest the last current state, failed approaches, open questions, and next
   steps before choosing an implementation.
4. If no handoff state exists and prior context is required, ask the user,
   "Where did we leave off?"
5. Verify remembered claims against the current working tree and external
   state. Current evidence is authoritative.

## Complete a task or end a session

Silently create or update `.ai-memory/HANDOFF.md` using this exact structure:

```markdown
# Session Handoff: [Brief Task Title]
- **Status:** [Completed / In-Progress / Blocked]
- **Current State:** [Where the code was left off]
- **What Worked:** [Architecture decisions, newly created files, endpoints verified]
- **Failed Approaches:** [What did not work and why]
- **Open Questions & Next Steps:** [What the next agent or session should address]
```

Keep entries factual and concise. Never put credentials, secrets, private user
data, hidden chain-of-thought, or unverifiable claims in memory files. A
handoff summarizes outcomes and evidence, not private reasoning.

## Rules and facts

- **Rules** prescribe how contributors should work. Store durable rules in
  `CLAUDE.md`, `AGENTS.md`, or another repository instruction file.
- **Facts** describe the observed project or environment, such as an actual
  service port or a verified runtime constraint. Store approved durable facts
  in `.ai-memory/FACTS.md`.
- Before appending a newly discovered fact, show the proposed wording and ask
  the user for approval. Do not treat guesses, temporary machine state, or
  unverified conclusions as durable facts.
- Handoff updates do not require separate approval; they are task records, not
  permanent project facts.

## Shareable engineering record

Put durable architecture decisions, structural notes, and code summaries in
repository Markdown rather than relying only on harness-specific memory.
Prefer links to authoritative repository files and commands that another
contributor can inspect.

## Code and completion quality

- Never submit placeholders, omitted bodies, or truncated code such as
  `TODO: rest of code`. Implement complete, syntactically valid behavior.
- Before declaring completion, state and run a concrete verification method
  appropriate to the change, such as a focused test, lint/type check, CLI
  invocation, or manual request.
- Record the verification command and outcome in the handoff. If verification
  cannot run, mark the work In-Progress or Blocked and explain why.
