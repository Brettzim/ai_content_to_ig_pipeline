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

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

import config
import ig_web_client as web

log = logging.getLogger("auto_commenter")

DEFAULT_CONFIG_PATH = config.BASE_DIR / "personas" / "auto_comment_config.json"


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

    for target in targets:
        comment_text = pick_comment()
        stats["attempted"] += 1
        log.info(f"[{account_name}] → target={target!r}  comment={comment_text!r}")

        if dry_run:
            log.info(f"[{account_name}] (dry-run) would comment on {target}")
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
                log.info(f"[{account_name}] ✓ commented on {target}")
            else:
                stats["failed"].append({"target": target, "reason": "comment_submit_failed"})
        except Exception as e:
            log.exception(f"[{account_name}] target {target!r} crashed: {e}")
            stats["failed"].append({"target": target, "reason": str(e)})
        finally:
            web.close_post_view(page)

        delay = _pick_delay(delay_between_targets, (25.0, 70.0))
        log.info(f"[{account_name}] waiting {delay:.1f}s before next target")
        time.sleep(delay)

    return stats


def run(config_path: Path = DEFAULT_CONFIG_PATH,
        only_account: str | None = None,
        dry_run: bool = False) -> list[dict]:
    cfg = _load_config(config_path)
    comments: list[str] = cfg.get("comments", [])
    accounts_cfg: dict[str, list[str]] = cfg.get("accounts", {})
    between_targets = cfg.get("delay_between_targets_s", [25, 70])
    between_accounts = cfg.get("delay_between_accounts_s", [60, 180])

    if not comments:
        raise ValueError("Config has empty 'comments' bank")
    if not accounts_cfg:
        raise ValueError("Config has no 'accounts' entries")

    items = list(accounts_cfg.items())
    if only_account:
        items = [(n, t) for (n, t) in items if n == only_account]
        if not items:
            raise KeyError(f"Account {only_account!r} not found in config")

    first_account = items[0][0]
    # First account's session must exist — log in if it doesn't
    web.ensure_session(first_account)

    all_stats: list[dict] = []

    with sync_playwright() as p:
        try:
            context, page = web.open_authenticated_page(p, first_account)
        except RuntimeError as e:
            log.warning(f"[{first_account}] session rejected ({e}) — re-logging in")
            web.login(first_account)
            context, page = web.open_authenticated_page(p, first_account)

        try:
            for idx, (name, targets) in enumerate(items):
                log.info(f"=== Starting account {name} ({len(targets)} targets) ===")

                # For accounts after the first, switch via IG's native flow
                if idx > 0:
                    switched = False
                    try:
                        switched = web.switch_account(page, name)
                    except Exception as e:
                        log.exception(f"[{name}] switch_account raised: {e}")
                    if not switched:
                        log.error(f"[{name}] could not switch — skipping account")
                        all_stats.append({
                            "account": name, "attempted": 0, "succeeded": 0,
                            "failed": [{"target": "<switch>", "reason": "switch_account failed"}],
                        })
                        continue

                picker = _make_comment_picker(comments)

                if not targets:
                    log.info(f"[{name}] no targets — skipping")
                    all_stats.append({"account": name, "attempted": 0,
                                      "succeeded": 0, "failed": []})
                else:
                    stats = _process_account_on_page(
                        page, name, targets, picker, between_targets, dry_run,
                    )
                    all_stats.append(stats)
                    log.info(f"=== {name} done: {stats['succeeded']}/{stats['attempted']} ok, "
                             f"{len(stats['failed'])} failed ===")

                if idx < len(items) - 1:
                    delay = _pick_delay(between_accounts, (60.0, 180.0))
                    log.info(f"Waiting {delay:.1f}s before next account")
                    time.sleep(delay)
        finally:
            # Persist session state for the first account on the way out
            try:
                state_file = web._session_path(first_account)
                context.storage_state(path=str(state_file))
            except Exception:
                pass
            context.close()

    return all_stats


def main():
    parser = argparse.ArgumentParser(description="Instagram auto-commenter")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH,
                        help="Path to auto_comment_config.json")
    parser.add_argument("--account", type=str, default=None,
                        help="Run only for this account name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log actions without posting comments")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    results = run(args.config, only_account=args.account, dry_run=args.dry_run)
    total_ok = sum(r["succeeded"] for r in results)
    total_try = sum(r["attempted"] for r in results)
    log.info(f"ALL DONE — {total_ok}/{total_try} comments posted across "
             f"{len(results)} account(s)")


if __name__ == "__main__":
    main()
