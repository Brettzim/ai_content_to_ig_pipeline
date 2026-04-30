"""
Auto-commenter — opens ONE browser session and cycles through accounts using
Instagram's native Switch-accounts feature. For each account it visits every
configured target page, opens the most recent non-pinned post, and leaves a
random comment from the shared comment bank.

Config file (JSON):
  personas/auto_comment_config.json   (copy from .example.json)

Prereq: all accounts must already be added to the same browser session
(multi-login). The first account in the config is the entry point — its
saved session must already contain the other accounts under "Switch accounts".
If it doesn't, log in to each account manually once via the IG web UI and save
state with `python ig_web_client.py login <name>`.

Run:
  venv\\Scripts\\python auto_commenter.py
  venv\\Scripts\\python auto_commenter.py --account valentina_vixen
  venv\\Scripts\\python auto_commenter.py --dry-run
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _pathsetup  # noqa: F401

import argparse
import json
import logging
import random
import threading
import time

from playwright.sync_api import Page, sync_playwright

import config
import ig_web_client as web

log = logging.getLogger("auto_commenter")

DEFAULT_USER = "brett"


def _load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Auto-comment config missing: {path}. "
            "Copy personas/auto_comment_config.example.json and fill it in."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _pick_delay(value, default: tuple[float, float]) -> float:
    lo, hi = default
    if isinstance(value, list) and len(value) == 2:
        lo, hi = float(value[0]), float(value[1])
    elif isinstance(value, (int, float)):
        return float(value)
    return random.uniform(lo, hi)


def _make_comment_picker(comments: list[str]):
    pool: list[str] = []

    def pick() -> str:
        nonlocal pool
        if not pool:
            pool = list(comments)
            random.shuffle(pool)
        return pool.pop()

    return pick


def _process_account_on_page(page: Page, account_name: str, targets: list[str],
                             pick_comment, delay_between_targets,
                             dry_run: bool) -> dict:
    """Run the comment loop for one account on an already-authenticated page."""
    stats = {"account": account_name, "attempted": 0, "succeeded": 0, "failed": []}

    for t_idx, target in enumerate(targets):
        comment_text = pick_comment()
        stats["attempted"] += 1

        if dry_run:
            stats["succeeded"] += 1
            continue

        try:
            ok = web.search_and_open_top_post(page, target, account_name)
            if not ok:
                stats["failed"].append({"target": target, "reason": "post_view_not_loaded"})
                web.close_post_view(page)
                continue

            time.sleep(random.uniform(1.5, 3.0))
            posted = web._post_comment(page, comment_text, account_name)
            if posted:
                stats["succeeded"] += 1
                log.info(f"[{account_name}] commented on {target}: \"{comment_text}\"")
            else:
                stats["failed"].append({"target": target, "reason": "comment_submit_failed"})
        except Exception as e:
            stats["failed"].append({"target": target, "reason": str(e)})
        finally:
            web.close_post_view(page)

        if t_idx < len(targets) - 1:
            delay = _pick_delay(delay_between_targets, (25.0, 70.0))
            time.sleep(delay)

    return stats


def _process_one_account(name: str, targets: list[str],
                         comments: list[str], between_targets,
                         dry_run: bool) -> dict:
    """Open `name`'s own session, post comments, persist state, close."""
    try:
        web.ensure_session(name)
    except Exception as e:
        return {"account": name, "attempted": 0, "succeeded": 0,
                "failed": [{"target": "<session>", "reason": str(e)}]}

    with sync_playwright() as p:
        try:
            context, page = web.open_authenticated_page(p, name)
        except RuntimeError as e:
            try:
                web.login(name)
                context, page = web.open_authenticated_page(p, name)
            except Exception as e2:
                return {"account": name, "attempted": 0, "succeeded": 0,
                        "failed": [{"target": "<login>", "reason": str(e2)}]}

        try:
            picker = _make_comment_picker(comments)
            stats = _process_account_on_page(
                page, name, targets, picker, between_targets, dry_run,
            )
            return stats
        finally:
            try:
                state_file = web._session_path(name)
                context.storage_state(path=str(state_file))
            except Exception:
                pass
            context.close()


def _worker_loop(queue: list[tuple[str, list[str]]],
                 queue_lock: threading.Lock, comments: list[str],
                 between_targets, between_accounts, dry_run: bool,
                 out_stats: list[dict], stats_lock: threading.Lock) -> None:
    """Pull accounts off the shared queue one at a time until empty."""
    first = True
    while True:
        with queue_lock:
            if not queue:
                return
            name, targets = queue.pop(0)

        if not first:
            delay = _pick_delay(between_accounts, (60.0, 180.0))
            time.sleep(delay)
        first = False

        if not targets:
            result = {"account": name, "attempted": 0, "succeeded": 0, "failed": []}
        else:
            try:
                result = _process_one_account(
                    name, targets, comments, between_targets, dry_run,
                )
            except Exception as e:
                result = {"account": name, "attempted": 0, "succeeded": 0,
                          "failed": [{"target": "<worker>", "reason": str(e)}]}

        with stats_lock:
            out_stats.append(result)


def run(config_path: Path,
        only_account: str | None = None,
        dry_run: bool = False,
        parallel_workers: int = 2) -> list[dict]:
    cfg = _load_config(config_path)
    comments: list[str] = cfg.get("comments", [])
    # New shape: {"assignments": {girl: [targets]}}. Legacy: {"accounts": {...}}.
    accounts_cfg: dict[str, list[str]] = cfg.get("assignments") or cfg.get("accounts") or {}
    between_targets = cfg.get("delay_between_targets_s", [25, 70])
    between_accounts = cfg.get("delay_between_accounts_s", [60, 180])

    if not comments:
        raise ValueError("Config has empty 'comments' bank")
    if not accounts_cfg:
        raise ValueError("Config has no 'assignments' entries")

    items = [(n, t) for n, t in accounts_cfg.items() if t]
    if only_account:
        items = [(n, t) for (n, t) in items if n == only_account]
        if not items:
            raise KeyError(f"Account {only_account!r} not found in config")
    if not items:
        return []

    n_workers = max(1, min(parallel_workers, len(items)))
    queue: list[tuple[str, list[str]]] = list(items)
    queue_lock = threading.Lock()
    all_stats: list[dict] = []
    stats_lock = threading.Lock()

    threads: list[threading.Thread] = []
    for wid in range(n_workers):
        t = threading.Thread(
            target=_worker_loop,
            args=(queue, queue_lock, comments, between_targets,
                  between_accounts, dry_run, all_stats, stats_lock),
            daemon=True,
        )
        t.start()
        threads.append(t)
        # Small stagger so browsers don't collide opening IG at the same instant
        if wid < n_workers - 1:
            time.sleep(1.5)
    for t in threads:
        t.join()
    return all_stats


def main():
    parser = argparse.ArgumentParser(description="Instagram auto-commenter")
    parser.add_argument("--user", type=str, default=DEFAULT_USER,
                        help=f"User whose data to use (default: {DEFAULT_USER})")
    parser.add_argument("--config", type=Path, default=None,
                        help="Path to auto_comment_config.json (default: <user>/auto_comment_config.json)")
    parser.add_argument("--account", type=str, default=None,
                        help="Run only for this account name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log actions without posting comments")
    parser.add_argument("--workers", type=int, default=2,
                        help="Number of parallel browser sessions (default 2)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    user_dir = config.AI_DIR / "users" / args.user
    config.WEB_CREDENTIALS_FILE = user_dir / "web_credentials.json"
    config.SESSIONS_DIR = config.SESSIONS_DIR / args.user
    cfg_path = args.config or (user_dir / "auto_comment_config.json")

    run(cfg_path, only_account=args.account, dry_run=args.dry_run,
        parallel_workers=args.workers)


if __name__ == "__main__":
    main()
