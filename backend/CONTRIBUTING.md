# Contributing

This document is the reference repo's own missing piece, flagged in an architecture audit:
neither `ARCHITECTURE.md` nor bold's own real monorepo document branch naming, commit
messages, or the PR checklist anywhere — so this is written fresh, not copied from a source
that doesn't have it. Update it in place once a team actually adopts this template and any
detail here needs to change for their real workflow (ticket tracker, review policy, etc.).

## Before you start

```bash
make install   # uv sync --all-extras
make hooks     # installs the pre-commit + commit-msg git hooks below
make dev-up    # Postgres via docker-compose, if you need to run anything locally
```

`make hooks` only needs to run once per clone (or again if `.pre-commit-config.yaml`
itself changes and you want the updated hook binaries).

## Branch naming

```
nombre.apellido/tipo/TICKET-123-descripcion-corta
```

- `nombre.apellido` — lowercase, dot-separated, no accents.
- `tipo` — one of `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`, `style`,
  `build`, `ci`, `revert` (same vocabulary as the commit convention below).
- `TICKET-123` — the tracker's issue key. If a change genuinely has no ticket (a typo fix,
  say), that's a call for the team to make explicitly — this template doesn't invent an
  "NOTICKET" escape hatch on its own.
- `descripcion-corta` — lowercase kebab-case, a few words, not the full sentence.

Example: `miguel.polo/feat/BACK-482-agregar-endpoint-cancelacion`

Enforced by the `branch-name` pre-commit hook (`scripts/check_branch_name.py`) on every
commit — `main`/`master` are exempt (and separately protected by `no-commit-to-branch`, so
nobody commits to them directly regardless of the branch's own name).

## Commit messages

```
tipo: #ticket descripción
```

Same `tipo` vocabulary as the branch name, an optional `(scope)` right after it (e.g.
`feat(orders): #482 ...`), the ticket number prefixed with `#`, then a short, present-tense
description of *why*, not a restatement of the diff.

Example: `feat: #482 agrega endpoint de cancelación de orden`

Enforced by the `commit-message` pre-commit hook (`scripts/check_commit_message.py`, the
`commit-msg` git stage) — merge commits, `git revert` commits, and `fixup!`/`squash!` markers
are exempt, everything else must match.

## Pull requests

Every PR gets the same automated gate, twice — once locally (pre-commit, fast, on every
commit) and once again in CI (`.github/workflows/ci.yml`, the final gate, can't be skipped
with `--no-verify`):

1. `ruff format --check` — formatting
2. `ruff check` — lint
3. `mypy src` — types
4. `lint-imports` — the 6 import-linter contracts (`ARCHITECTURE.md` §16)
5. `pytest -m unit` — unit tests

Before opening a PR:

```bash
make check   # lint + typecheck + imports + test-unit — the same 4 checks CI runs
```

A PR description should say what changed and why, link the ticket, and note what was tested
(unit / integration / manually). There's no separate PR template file yet — add one
(`.github/pull_request_template.md`) once the team has agreed on what it should ask for;
this document intentionally doesn't invent one on its own.

## What pre-commit does *not* enforce

`pytest -m unit` runs in CI, not in the pre-commit hook — a full (even if fast) test run on
every single `git commit` is a different tradeoff than gating format/lint/types/imports,
and this template doesn't force that choice for you. If your team wants it in pre-commit
too, add a `local` hook calling `uv run pytest -m unit` the same way the others in
`.pre-commit-config.yaml` do.
