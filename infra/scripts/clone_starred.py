#!/usr/bin/env python3
"""Clone an operator's GitHub-starred repos into a LOCAL, gitignored corpus.

Use case: while we (the CLI coding agents - Claude / Codex / Gemini)
develop SelfFork itself, MANDATE 9 (Korpus Refleks) tells us to consult
relevant prior art before each architectural decision.
``examples_crucial/`` (29 locked rivals) and ``examples/`` (60
secondary) cover the project's canonical corpus. THIS script adds a
THIRD layer - the operator's own curated GitHub stars - pulled locally
so we can grep / read / cite them during development.

DEV-time only. Static. Not the runtime starred-RAG pool (that one lives
in Mind's GLOBAL pool under ``~/.selffork/...``, auto-synced, chunked +
embedded - see ``s-vision-candidates-github-rag-2026-05-24`` memory).

The corpus directory (default ``examples_starred/``) is gitignored, so
nothing leaves the workstation; each forker runs this script for their
OWN starred list and gets their OWN corpus. Fork-friendly.

Usage:
    python infra/scripts/clone_starred.py --user <github-username>

    # With a PAT to avoid the 60 req/hr unauthenticated rate-limit
    # (no scopes needed for listing public stars):
    GITHUB_TOKEN=<pat> python infra/scripts/clone_starred.py --user <user>

    # Faster with parallel workers (git/network parallelizes well):
    python infra/scripts/clone_starred.py --user <user> --jobs 8

    # Custom target directory:
    python infra/scripts/clone_starred.py --user <user> --dir custom_dir

Idempotent: existing FULLY-CLONED repos are ``git fetch``ed; partial /
interrupted clones (no ``.git/HEAD``) are wiped and re-cloned fresh; new
repos are shallow-cloned. Un-starred-since clones are left in place
(operator decides whether to delete).

Stdlib-only (urllib + subprocess + concurrent.futures + argparse) - no
external dependency added to the project.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
PER_PAGE = 100
USER_AGENT = "selffork-clone-starred"
# Resolve git's absolute path once (eliminates ruff S607 partial-path
# warnings; falls back to "git" if PATH lookup fails, in which case the
# subprocess call surfaces a clear error if git isn't installed).
GIT = shutil.which("git") or "git"


def list_starred(user: str, token: str | None) -> list[dict[str, Any]]:
    """Return every starred repo for ``user`` (paginated)."""
    page = 1
    repos: list[dict[str, Any]] = []
    while True:
        url = (
            f"{GITHUB_API}/users/{user}/starred"
            f"?per_page={PER_PAGE}&page={page}"
        )
        # Hardcoded https://api.github.com base above; user-supplied path
        # segment is escaped by the GitHub URL convention. Safe scheme.
        req = urllib.request.Request(url)  # noqa: S310
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", USER_AGENT)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310
                data = json.load(resp)
        except urllib.error.HTTPError as exc:
            print(
                f"GitHub API error (page {page}): {exc}",
                file=sys.stderr,
            )
            if exc.code == 403:
                print(
                    "Rate-limited (60 req/hr unauth). Set GITHUB_TOKEN env "
                    "var with a PAT (no scopes needed for public repos).",
                    file=sys.stderr,
                )
            sys.exit(1)
        if not data:
            break
        repos.extend(data)
        if len(data) < PER_PAGE:
            break
        page += 1
    return repos


def clone_or_fetch(repo: dict[str, Any], target_dir: Path) -> str:
    """Shallow-clone a repo if absent / partial; ``git fetch`` if fully cloned.

    A *populated* clone has ``dest/.git/HEAD``. Anything else (empty dir,
    interrupted previous run, missing .git) is treated as needing a
    fresh clone - wipe + re-clone. Returns a short status string for
    the run summary.
    """
    owner = repo["owner"]["login"]
    name = repo["name"]
    clone_url = repo["clone_url"]
    dest = target_dir / owner / name
    if dest.exists() and (dest / ".git" / "HEAD").is_file():
        try:
            subprocess.run(  # noqa: S603
                [GIT, "-C", str(dest), "fetch", "--depth=1", "--quiet"],
                check=True,
            )
        except subprocess.CalledProcessError:
            return "fetch-failed"
        return "fetched"
    if dest.exists():
        # Partial / interrupted clone - wipe and start fresh.
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(  # noqa: S603
            [GIT, "clone", "--depth=1", "--quiet", clone_url, str(dest)],
            check=True,
        )
    except subprocess.CalledProcessError:
        return "clone-failed"
    return "cloned"


def write_manifest(
    target_dir: Path,
    user: str,
    repos: list[dict[str, Any]],
) -> Path:
    """Write a gitignored at-a-glance index of the corpus.

    The manifest itself sits inside ``target_dir`` and rides along with
    the gitignore on the parent directory, so it never reaches the repo.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Starred corpus for `{user}`",
        "",
        f"_Generated {datetime.now(UTC).isoformat()} - {len(repos)} repos._",
        "",
        "| Owner / Repo | Stars | Lang | Description |",
        "|---|---|---|---|",
    ]
    for r in repos:
        owner = r["owner"]["login"]
        name = r["name"]
        stars = r.get("stargazers_count", "?")
        lang = r.get("language") or "-"
        desc = (r.get("description") or "").replace("|", "\\|")[:120]
        lines.append(f"| `{owner}/{name}` | {stars} | {lang} | {desc} |")
    manifest = target_dir / "MANIFEST.md"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Clone the operator's GitHub-starred repos into a local, "
            "gitignored dev corpus (MANDATE 9 - Korpus Refleks)."
        ),
    )
    ap.add_argument(
        "--user",
        required=True,
        help="GitHub username whose starred list to clone.",
    )
    ap.add_argument(
        "--dir",
        default="examples_starred",
        help="Target directory (default: examples_starred/).",
    )
    ap.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub PAT (also reads GITHUB_TOKEN env var).",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Parallel clone workers (default: 1 sequential; "
            "4-8 recommended for speed; git/network parallelizes well)."
        ),
    )
    args = ap.parse_args()

    target_dir = Path(args.dir).resolve()
    print(f"Listing {args.user}'s starred repos...", flush=True)
    repos = list_starred(args.user, args.token)
    print(
        f"Found {len(repos)} starred repos. Cloning into {target_dir}/ "
        f"(jobs={args.jobs})",
        flush=True,
    )
    stats: dict[str, int] = {}
    if args.jobs <= 1:
        for r in repos:
            status = clone_or_fetch(r, target_dir)
            stats[status] = stats.get(status, 0) + 1
            owner = r["owner"]["login"]
            name = r["name"]
            print(f"  [{status:>13}] {owner}/{name}", flush=True)
    else:
        # ThreadPoolExecutor is safe here: each clone is an out-of-process
        # subprocess (git), so the GIL doesn't matter; threads only
        # orchestrate. Each repo gets a unique destination directory, so
        # there is no inter-thread contention on the filesystem.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.jobs,
        ) as executor:
            futures = {
                executor.submit(clone_or_fetch, r, target_dir): r
                for r in repos
            }
            for fut in concurrent.futures.as_completed(futures):
                r = futures[fut]
                status = fut.result()
                stats[status] = stats.get(status, 0) + 1
                owner = r["owner"]["login"]
                name = r["name"]
                print(f"  [{status:>13}] {owner}/{name}", flush=True)
    manifest = write_manifest(target_dir, args.user, repos)
    print(flush=True)
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}", flush=True)
    print(f"Manifest: {manifest}", flush=True)


if __name__ == "__main__":
    main()
