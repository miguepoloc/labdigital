#!/usr/bin/env python3
"""pre-commit local hook — validates the current branch name against this repo's
convention: `nombre.apellido/tipo/ticket-descripcion-corta` (CONTRIBUTING.md).

Runs on every commit (not just on branch creation) because pre-commit has no
"on checkout" stage — cheap enough (one `git` call, one regex) to not matter."""

import re
import subprocess
import sys

_PATTERN = re.compile(
    r"^[a-z]+\.[a-z]+/"  # nombre.apellido
    r"(feat|fix|chore|refactor|test|docs|perf|style|build|ci|revert)/"  # tipo
    r"[A-Za-z][A-Za-z0-9]*-\d+-"  # TICKET-123-
    r"[a-z0-9]+(-[a-z0-9]+)*$"  # descripcion-corta
)

# Branches that never get a ticket-shaped name and are never committed to directly by this
# hook's target audience anyway — checked so a maintainer working on this template itself, or
# CI's detached-HEAD checkout, doesn't get blocked.
_EXEMPT = {"main", "master", "HEAD"}


def _current_branch() -> str:
    """`symbolic-ref`, not `rev-parse --abbrev-ref HEAD`: the latter needs `HEAD` to resolve
    to an actual commit, which doesn't exist yet on a repo's very first commit (an "unborn"
    branch) — exactly when this hook also needs to run."""
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> int:
    branch = _current_branch()
    if branch in _EXEMPT or _PATTERN.match(branch):
        return 0
    print(
        f"Nombre de rama inválido: '{branch}'\n"
        "Formato esperado: nombre.apellido/tipo/TICKET-123-descripcion-corta\n"
        "tipo: feat | fix | chore | refactor | test | docs | perf | style | build | ci | revert\n"
        "Ejemplo: miguel.polo/feat/BACK-482-agregar-endpoint-cancelacion\n"
        "Ver CONTRIBUTING.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
