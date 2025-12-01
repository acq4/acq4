# CLAUDE.md

This file provides Claude-specific guidance when working with code in this repository. For project-wide practices, environment setup, architectural notes, and tooling expectations, see `AGENTS.md`.

## Git Commit Standards
- When committing changes that Claude wrote, include "(claude)" in an explicit --author
- Use the standard commit message format:
```
<type>: <description>

<optional detailed explanation>

🤖 Generated with [Claude Code](https://claude.ai/code)
```
- Commit types: feat, fix, docs, style, refactor, perf, test, chore
