"""
Instagram Web Client — Playwright + stealth path.

Separate from instagram_client.py (Graph API). Used for features the Graph API
doesn't expose cleanly (e.g. DM inbox browsing, story interactions).

Strategy (per latenode bot-detection guide):
  - Chromium launched with --disable-blink-features=AutomationControlled
  - tf-playwright-stealth patches navigator.webdriver, plugins, WebGL, canvas, etc.
  - Persistent storage_state.json per account so login only happens on first run
  - Human-like randomized delays between keystrokes and navigations
  - Headful by default (safer for initial login + manual 2FA solve)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _pathsetup  # noqa: F401

import json
import logging
import random
import time
from typing import Optional

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright_stealth import stealth_sync

import config

log = logging.getLogger(__name__)

IG_URL = "https://www.instagram.com/"
IG_LOGIN_URL = "https://www.instagram.com/accounts/login/"

REALISTIC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _human_delay(min_s: float = 0.4, max_s: float = 1.2) -> None:
    time.sleep(random.uniform(min_s, max_s))


def _type_human(page: Page, selector: str, text: str) -> None:
    page.click(selector)
    _human_delay(0.2, 0.5)
    for ch in text:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.05, 0.18))


def _load_credentials(account_name: str) -> dict:
    if not config.WEB_CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Web credentials file missing: {config.WEB_CREDENTIALS_FILE}. "
            "Copy personas/web_credentials.example.json and fill it in."
        )
    with open(config.WEB_CREDENTIALS_FILE, encoding="utf-8") as f:
        creds = json.load(f)
    for entry in creds:
        if entry.get("name") == account_name:
            return entry
    raise KeyError(f"No web credentials for account '{account_name}'")


def _session_path(account_name: str) -> Path:
    path = config.SESSIONS_DIR / account_name
    path.mkdir(parents=True, exist_ok=True)
    return path / "storage_state.json"


def _new_context(p: Playwright, storage_state: Optional[Path]) -> BrowserContext:
    browser = p.chromium.launch(
        headless=config.WEB_HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent=REALISTIC_UA,
        locale="en-US",
        timezone_id="America/New_York",
        storage_state=str(storage_state) if storage_state and storage_state.exists() else None,
    )
    return context


def _is_logged_in(page: Page) -> bool:
    """Quick check — IG redirects unauthenticated users to /accounts/login/."""
    try:
        page.goto(IG_URL, wait_until="domcontentloaded", timeout=20000)
        _human_delay(1.5, 2.5)
        url = page.url
        if "accounts/login" in url:
            return False
        # Logged-in home shows a nav with a "New post" / home icon
        return page.locator('svg[aria-label="Home"]').count() > 0
    except Exception as e:
        log.warning(f"Login check failed: {e}")
        return False


def login(account_name: str) -> None:
    """
    Open instagram.com and log in as `account_name`. Saves storage_state on success
    so subsequent runs reuse the cookie/session.
    """
    creds = _load_credentials(account_name)
    state_file = _session_path(account_name)

    with sync_playwright() as p:
        context = _new_context(p, state_file)
        page = context.new_page()
        stealth_sync(page)

        if state_file.exists() and _is_logged_in(page):
            log.info(f"[{account_name}] already logged in — session reused")
            context.storage_state(path=str(state_file))
            context.close()
            return

        log.info(f"[{account_name}] no valid session — performing login")
        page.goto(IG_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        _human_delay(2.0, 3.5)

        # Dismiss any cookie / consent modal — IG uses several variants
        for btn_name in (
            "Allow all cookies",
            "Only allow essential cookies",
            "Allow essential and optional cookies",
            "Accept All",
            "Accept",
        ):
            try:
                page.get_by_role("button", name=btn_name).click(timeout=2000)
                log.info(f"[{account_name}] clicked consent button: {btn_name}")
                _human_delay(0.8, 1.5)
                break
            except Exception:
                continue

        # Find the username input — IG's attributes shift, so try several
        # strategies. Fall back to the first form text input as a last resort.
        username_input = None
        for sel in (
            'input[name="username"]',
            'input[aria-label*="username" i]',
            'input[autocomplete="username"]',
            'form input[type="text"]',
        ):
            loc = page.locator(sel).first
            try:
                loc.wait_for(state="visible", timeout=8000)
                username_input = loc
                log.info(f"[{account_name}] matched username via: {sel}")
                break
            except Exception:
                continue

        if username_input is None:
            shot = config.SESSIONS_DIR / account_name / "login_failed.png"
            page.screenshot(path=str(shot), full_page=True)
            log.error(f"[{account_name}] username field not found — screenshot: {shot}")
            log.error(f"[{account_name}] current URL: {page.url}")
            raise RuntimeError("Could not locate username input")

        password_input = page.locator('input[type="password"]').first
        password_input.wait_for(state="visible", timeout=10000)

        username_input.click()
        _human_delay(0.2, 0.5)
        for ch in creds["username"]:
            page.keyboard.type(ch)
            time.sleep(random.uniform(0.05, 0.18))
        _human_delay(0.5, 1.2)

        password_input.click()
        _human_delay(0.2, 0.5)
        for ch in creds["password"]:
            page.keyboard.type(ch)
            time.sleep(random.uniform(0.05, 0.18))
        _human_delay(0.6, 1.4)

        for sel in (
            'button[type="submit"]',
            'button:has-text("Log in")',
            'div[role="button"]:has-text("Log in")',
        ):
            try:
                page.locator(sel).first.click(timeout=3000)
                break
            except Exception:
                continue
        log.info(f"[{account_name}] submitted credentials — waiting for home or challenge")

        # Wait up to 90s for either the home nav to appear, or a 2FA/challenge
        # screen the user can solve manually (headful mode).
        try:
            page.wait_for_selector(
                'svg[aria-label="Home"], input[name="verificationCode"], text=/suspicious|challenge/i',
                timeout=90000,
            )
        except Exception:
            log.warning(f"[{account_name}] no known post-login state seen in 90s")

        # Give the user time to solve any manual challenge
        if not config.WEB_HEADLESS:
            log.info(f"[{account_name}] if a challenge/2FA is shown, solve it now (waiting 120s)")
            try:
                page.wait_for_selector('svg[aria-label="Home"]', timeout=120000)
            except Exception:
                pass

        # Dismiss "Save login info?" and "Turn on notifications?" prompts
        for label in ("Not Now", "Not now"):
            try:
                page.get_by_role("button", name=label).click(timeout=3000)
                _human_delay(0.5, 1.0)
            except Exception:
                pass

        if page.locator('svg[aria-label="Home"]').count() == 0:
            context.storage_state(path=str(state_file))
            context.close()
            raise RuntimeError(
                f"[{account_name}] login did not reach home feed — check for 2FA/challenge"
            )

        context.storage_state(path=str(state_file))
        log.info(f"[{account_name}] login successful — session saved to {state_file}")
        context.close()


def _post_comment(page: Page, text: str, account_name: str) -> bool:
    """
    Type `text` into the "Add a comment..." input and click Post.
    Scoped strictly to the form containing the comment textarea so we never
    accidentally click neighboring action buttons (like / repost / share).
    """
    # Locate the form that contains an "Add a comment" input
    form = page.locator('form:has(textarea[aria-label*="Add a comment" i])').first
    try:
        form.wait_for(state="visible", timeout=8000)
    except Exception:
        # Fall back to form with placeholder match
        form = page.locator('form:has(textarea[placeholder*="Add a comment" i])').first
        try:
            form.wait_for(state="visible", timeout=4000)
        except Exception:
            shot = config.SESSIONS_DIR / account_name / "comment_box_failed.png"
            page.screenshot(path=str(shot), full_page=True)
            log.error(f"[{account_name}] comment form not found — screenshot: {shot}")
            return False

    textarea = form.locator('textarea').first
    try:
        box = textarea.bounding_box()
        log.info(f"[{account_name}] comment textarea box={box}")
    except Exception:
        pass

    # Focus + type — no click (click has been triggering neighbor elements).
    # Playwright focuses automatically via JS; then keyboard.type sends keystrokes.
    textarea.focus()
    _human_delay(0.3, 0.6)
    try:
        textarea.press_sequentially(text, delay=90)
    except AttributeError:
        textarea.type(text, delay=90)
    _human_delay(0.8, 1.4)
    log.info(f"[{account_name}] typed comment")

    pre_shot = config.SESSIONS_DIR / account_name / "comment_pre_submit.png"
    page.screenshot(path=str(pre_shot), full_page=False)

    # Post button — strictly inside this form
    post_btn = form.locator(':is(div[role="button"], button):has-text("Post")').first
    submitted_via = None
    try:
        post_btn.wait_for(state="visible", timeout=5000)
        post_btn.click(timeout=3000)
        submitted_via = "form Post button"
    except Exception as e:
        log.warning(f"[{account_name}] Post button inside form not clickable: {e}")
        # Last resort: press Enter while textarea is focused
        try:
            textarea.focus()
            page.keyboard.press("Enter")
            submitted_via = "Enter"
        except Exception:
            pass

    log.info(f"[{account_name}] submit attempted via: {submitted_via}")
    _human_delay(2.0, 3.0)

    post_shot = config.SESSIONS_DIR / account_name / "comment_post_submit.png"
    page.screenshot(path=str(post_shot), full_page=False)

    try:
        remaining = textarea.input_value().strip()
    except Exception:
        remaining = "<could not read>"
    log.info(f"[{account_name}] textarea after submit: {remaining!r}")

    if remaining and remaining == text:
        log.error(f"[{account_name}] comment text still in box — submit did NOT register")
        return False
    return True


def setup_multi_login(anchor_account: str) -> None:
    """
    Open a headful browser using the anchor account's saved session (logging in
    first if needed), then pause so the user can manually add the other
    accounts via IG's UI (Profile menu → Switch accounts → Add account, or
    "Log in with another account"). Saves the updated storage_state when the
    user presses Enter — that file then contains all added accounts.
    """
    ensure_session(anchor_account)
    state_file = _session_path(anchor_account)

    with sync_playwright() as p:
        # Force headful regardless of WEB_HEADLESS so the user can interact
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=REALISTIC_UA,
            locale="en-US",
            timezone_id="America/New_York",
            storage_state=str(state_file),
        )
        page = context.new_page()
        stealth_sync(page)
        page.goto(IG_URL, wait_until="domcontentloaded", timeout=30000)

        print("\n" + "=" * 70)
        print(f"Browser is open as '{anchor_account}'.")
        print("Add each additional account by going to your profile menu →")
        print('  "Switch accounts" → "Add account" (or "Log in with another account")')
        print("and completing login for each. Verify all expected accounts")
        print("appear under 'Switch accounts' before continuing.")
        print("When done, come back here and press ENTER to save state.")
        print("=" * 70 + "\n")

        try:
            input("Press ENTER when you've finished adding accounts... ")
        except (EOFError, KeyboardInterrupt):
            pass

        context.storage_state(path=str(state_file))
        log.info(f"Saved multi-login state to {state_file}")
        context.close()
        browser.close()


def ensure_session(account_name: str) -> None:
    """
    Guarantee a valid saved session for `account_name`. If no storage_state
    file exists, run the full login flow. Call this BEFORE
    open_authenticated_page when orchestrating multiple accounts back-to-back.
    """
    state_file = _session_path(account_name)
    if not state_file.exists():
        log.info(f"[{account_name}] no saved session — running login()")
        login(account_name)
        return
    log.info(f"[{account_name}] reusing saved session at {state_file}")


def open_authenticated_page(p: Playwright, account_name: str) -> tuple[BrowserContext, Page]:
    """Open a context+page reusing saved session. Raises if session missing/expired."""
    state_file = _session_path(account_name)
    if not state_file.exists():
        raise RuntimeError(f"No saved session for {account_name} — run login first")

    context = _new_context(p, state_file)
    page = context.new_page()
    stealth_sync(page)

    page.goto(IG_URL, wait_until="domcontentloaded", timeout=30000)
    _human_delay(1.5, 2.5)
    if "accounts/login" in page.url:
        context.close()
        raise RuntimeError(f"[{account_name}] session expired — run login again")
    return context, page


def search_and_open_top_post(page: Page, query: str, account_name: str) -> bool:
    """
    From a logged-in IG home page: open the search panel, type `query`,
    click the top result's profile, then open its most recent post.
    Returns True if the post view is loaded.
    """
    log.info(f"[{account_name}] opening search panel")
    search_btn = None
    for sel in (
        'a[role="link"]:has(svg[aria-label="Search"])',
        'div[role="button"]:has(svg[aria-label="Search"])',
        'svg[aria-label="Search"]',
    ):
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=5000)
            search_btn = loc
            break
        except Exception:
            continue

    if search_btn is None:
        shot = config.SESSIONS_DIR / account_name / "search_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        raise RuntimeError(f"Search button not found — screenshot: {shot}")

    search_btn.click()
    _human_delay(1.0, 1.8)

    search_input = None
    for sel in (
        'input[placeholder="Search"]',
        'input[aria-label="Search input"]',
        'input[aria-label*="Search" i]',
    ):
        loc = page.locator(sel).first
        try:
            loc.wait_for(state="visible", timeout=5000)
            search_input = loc
            break
        except Exception:
            continue

    if search_input is None:
        shot = config.SESSIONS_DIR / account_name / "search_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        raise RuntimeError(f"Search input not found — screenshot: {shot}")

    # Clear any prior query text before typing
    try:
        search_input.click()
        _human_delay(0.2, 0.4)
        search_input.fill("")
    except Exception:
        pass
    _human_delay(0.3, 0.6)
    for ch in query:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.06, 0.16))

    log.info(f"[{account_name}] typed query: {query!r} — waiting for results")
    _human_delay(2.0, 3.5)

    result_links = page.locator('a[role="link"][href^="/"]').all()
    results: list[dict] = []
    seen = set()
    for link in result_links:
        try:
            href = link.get_attribute("href") or ""
            if not href.startswith("/") or href.count("/") > 2:
                continue
            handle = href.strip("/").split("/")[0]
            if not handle or handle in seen:
                continue
            if handle in {"explore", "reels", "direct", "accounts", "p"}:
                continue
            results.append({"handle": handle})
            seen.add(handle)
        except Exception:
            continue

    if not results:
        shot = config.SESSIONS_DIR / account_name / "search_no_results.png"
        page.screenshot(path=str(shot), full_page=True)
        raise RuntimeError(f"No search results — screenshot: {shot}")

    top = results[0]
    log.info(f"[{account_name}] clicking top result: {top['handle']}")
    first_result = page.locator(f'a[role="link"][href="/{top["handle"]}/"]').first
    try:
        first_result.click(timeout=5000)
    except Exception:
        page.goto(f"{IG_URL}{top['handle']}/", wait_until="domcontentloaded")

    post_selector = 'main a[href*="/p/"], main a[href*="/reel/"]'
    try:
        page.wait_for_selector(post_selector, timeout=15000)
    except Exception:
        shot = config.SESSIONS_DIR / account_name / "profile_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        raise RuntimeError(f"Profile grid not found — screenshot: {shot}")

    _human_delay(1.5, 2.5)

    # Skip pinned posts. IG can render the pinned signal in different shapes:
    #   - an SVG with aria-label="Pinned post" (sibling overlay in the grid cell)
    #   - an SVG with a child <title>Pinned post</title>
    #   - a text node "Pinned" somewhere in the cell
    # Collect all grid links in a single page-level eval, walking up ancestors
    # and checking every signal. Up to 3 posts can be pinned.
    pinned_scan_js = """
        () => {
            const links = document.querySelectorAll(
                'main a[href*="/p/"], main a[href*="/reel/"]'
            );
            const out = [];
            for (const a of links) {
                let node = a;
                let pinned = false;
                let signal = null;
                for (let i = 0; i < 8 && node && !pinned; i++) {
                    for (const n of node.querySelectorAll('[aria-label]')) {
                        const v = (n.getAttribute('aria-label') || '').toLowerCase();
                        if (v.includes('pinned')) { pinned = true; signal = 'aria:' + v; break; }
                    }
                    if (pinned) break;
                    for (const t of node.querySelectorAll('title')) {
                        const v = (t.textContent || '').toLowerCase();
                        if (v.includes('pinned')) { pinned = true; signal = 'title:' + v; break; }
                    }
                    if (pinned) break;
                    const txt = (node.textContent || '').toLowerCase();
                    if (txt.includes('pinned')) {
                        // only count if short enough to not be a caption match
                        if (txt.length < 200) { pinned = true; signal = 'text'; }
                    }
                    node = node.parentElement;
                }
                out.push({ href: a.getAttribute('href'), pinned, signal });
            }
            return out;
        }
    """
    try:
        scan = page.evaluate(pinned_scan_js) or []
    except Exception as e:
        log.warning(f"[{account_name}] pinned scan failed: {e}")
        scan = []

    for idx, row in enumerate(scan[:6]):
        log.info(f"[{account_name}] grid[{idx}] pinned={row.get('pinned')} "
                 f"signal={row.get('signal')!r} href={row.get('href')}")

    all_posts = page.locator(post_selector).all()
    first_post = None
    post_href = None
    for idx, link in enumerate(all_posts):
        href = link.get_attribute("href")
        row = next((r for r in scan if r.get("href") == href), None)
        is_pinned = bool(row and row.get("pinned"))
        if is_pinned:
            log.info(f"[{account_name}] skipping pinned post at idx {idx}: {href}")
            continue
        first_post = link
        post_href = href
        log.info(f"[{account_name}] selected non-pinned post at idx {idx}: {href}")
        break

    if first_post is None:
        # Fallback — if we saw any pinned rows, skip that many; else first.
        pinned_count = sum(1 for r in scan if r.get("pinned"))
        skip_n = min(pinned_count, 3)
        log.warning(f"[{account_name}] walker matched no non-pinned link; "
                    f"falling back to idx {skip_n} (pinned_count={pinned_count})")
        posts_all = page.locator(post_selector)
        first_post = posts_all.nth(skip_n)
        post_href = first_post.get_attribute("href")

    log.info(f"[{account_name}] opening most recent post: {post_href}")

    first_post.scroll_into_view_if_needed()
    _human_delay(0.5, 1.0)

    clicked = False
    for attempt_sel, desc in (
        (first_post, "first post link"),
        (first_post.locator("img").first, "first post <img>"),
        (first_post.locator("div").first, "first post inner <div>"),
    ):
        try:
            attempt_sel.click(timeout=4000)
            clicked = True
            break
        except Exception:
            continue

    if not clicked and post_href:
        page.goto(f"https://www.instagram.com{post_href}", wait_until="domcontentloaded")

    try:
        page.wait_for_selector(
            'div[role="dialog"], article[role="presentation"], '
            'main article:has(video), main article:has(img)',
            timeout=10000,
        )
        log.info(f"[{account_name}] post view loaded")
        return True
    except Exception:
        shot = config.SESSIONS_DIR / account_name / "post_view_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        log.warning(f"[{account_name}] post view didn't match — screenshot: {shot}")
        return False


def _dismiss_switch_error(page: Page) -> None:
    """
    Freshly-reactivated accounts sometimes show a "Sorry, something went wrong"
    dialog right after the switch. IG wants two clicks: OK to dismiss, then
    Reload to retry the profile fetch. Both are best-effort — if neither
    button is present, we assume the switch went through cleanly.
    """
    dismissed = False
    for label in ("OK", "Ok", "Dismiss"):
        if dismissed:
            break
        for sel in (
            f'div[role="dialog"] div[role="button"]:has-text("{label}")',
            f'div[role="dialog"] button:has-text("{label}")',
            f'button:has-text("{label}")',
        ):
            try:
                page.locator(sel).first.click(timeout=400)
                log.info(f"[switch_account] dismissed error dialog via {label}")
                dismissed = True
                break
            except Exception:
                continue
    if not dismissed:
        return

    page.wait_for_timeout(200)
    for sel in (
        'div[role="button"]:has-text("Reload page")',
        'button:has-text("Reload page")',
        'div[role="button"]:has-text("Reload")',
        'button:has-text("Reload")',
    ):
        try:
            page.locator(sel).first.click(timeout=600)
            log.info(f"[switch_account] clicked Reload after error")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            return
        except Exception:
            continue


def switch_account(page: Page, target_account_name: str) -> bool:
    """
    Use IG's native "Switch accounts" flow to hop to another account on the
    same browser session. The target account must already be added to this
    session's multi-login (we do not handle the "Add account" path here).

    Resolves target_account_name → IG username via web_credentials.json.
    Returns True if the switch completed and the home feed loads as that user.
    """
    creds = _load_credentials(target_account_name)
    target_username = creds["username"]

    # Make sure we're on a page where the sidebar is visible
    try:
        page.goto(IG_URL, wait_until="domcontentloaded", timeout=20000)
        _human_delay(1.5, 2.5)
    except Exception:
        pass

    # Step 1: open the Switch-account entry point. IG offers two paths:
    #   (a) direct "Switch" button near the profile name in the sidebar
    #   (b) "More" hamburger → "Switch accounts" menu item
    opened = False
    for sel in (
        'div[role="button"]:has-text("Switch")',
        'button:has-text("Switch")',
    ):
        try:
            page.locator(sel).first.click(timeout=2500)
            opened = True
            log.info(f"[switch_account] opened via sidebar Switch: {sel}")
            break
        except Exception:
            continue

    if not opened:
        # Fallback: hamburger/"More" menu
        for sel in (
            'svg[aria-label="More options"]',
            'svg[aria-label="Settings"]',
            'div[role="button"]:has-text("More")',
        ):
            try:
                page.locator(sel).first.click(timeout=2500)
                _human_delay(0.6, 1.2)
                for item_sel in (
                    'div[role="button"]:has-text("Switch accounts")',
                    'a:has-text("Switch accounts")',
                    'button:has-text("Switch accounts")',
                ):
                    try:
                        page.locator(item_sel).first.click(timeout=2500)
                        opened = True
                        log.info(f"[switch_account] opened via More → {item_sel}")
                        break
                    except Exception:
                        continue
                if opened:
                    break
            except Exception:
                continue

    if not opened:
        shot = config.SESSIONS_DIR / target_account_name / "switch_menu_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        log.error(f"Could not open Switch accounts menu — screenshot: {shot}")
        return False

    _human_delay(1.0, 2.0)

    # Step 2: click the row for the target username inside the modal
    dialog = page.locator('div[role="dialog"]').last
    try:
        dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        dialog = page  # fall back to page-wide search

    row = dialog.locator(
        f':is(div[role="button"], button, a):has-text("{target_username}")'
    ).first
    try:
        row.wait_for(state="visible", timeout=5000)
        row.click(timeout=4000)
    except Exception as e:
        shot = config.SESSIONS_DIR / target_account_name / "switch_row_failed.png"
        page.screenshot(path=str(shot), full_page=True)
        log.error(
            f"Target username {target_username!r} not in Switch list "
            f"({e}) — screenshot: {shot}"
        )
        return False

    _human_delay(2.0, 3.5)

    # Step 2.5: some freshly-reactivated accounts show a "Sorry, something
    # went wrong" dialog immediately after the switch. The profile loads fine
    # once you dismiss OK and then press Reload. Handle both buttons if present.
    _dismiss_switch_error(page)

    # Step 3: verify the home feed loads. Reactivated accounts can take longer
    # after the Reload click, so retry with a fallback goto(IG_URL).
    for attempt in range(2):
        try:
            page.wait_for_selector('svg[aria-label="Home"]', timeout=20000)
            log.info(f"[switch_account] switched to {target_username}")
            return True
        except Exception:
            if attempt == 0:
                log.info(f"[switch_account] Home svg not visible, retrying via goto")
                try:
                    page.goto(IG_URL, wait_until="domcontentloaded", timeout=20000)
                    _human_delay(1.5, 2.5)
                except Exception:
                    pass
                continue
            shot = config.SESSIONS_DIR / target_account_name / "switch_verify_failed.png"
            page.screenshot(path=str(shot), full_page=True)
            log.error(f"Home feed not visible after switch — screenshot: {shot}")
            return False


def close_post_view(page: Page) -> None:
    """Close the post dialog by pressing Escape and/or navigating home."""
    try:
        page.keyboard.press("Escape")
        _human_delay(0.5, 1.0)
    except Exception:
        pass
    try:
        page.goto(IG_URL, wait_until="domcontentloaded", timeout=20000)
        _human_delay(1.0, 2.0)
    except Exception:
        pass


def search(account_name: str, query: str, comment: Optional[str] = None, pause_s: int = 15) -> None:
    """CLI entry point — logs in, searches, opens top post, optionally comments."""
    with sync_playwright() as p:
        context, page = open_authenticated_page(p, account_name)
        try:
            ok = search_and_open_top_post(page, query, account_name)
            if ok and comment:
                _human_delay(1.0, 2.0)
                log.info(f"[{account_name}] posting comment: {comment!r}")
                if not _post_comment(page, comment, account_name):
                    log.error(f"[{account_name}] comment submission failed")
            _human_delay(1.5, 2.5)
            log.info(f"[{account_name}] keeping browser open {pause_s}s")
            time.sleep(pause_s)
        finally:
            context.close()


if __name__ == "__main__":
    import sys
    import traceback

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    usage = (
        "Usage:\n"
        "  python ig_web_client.py login  <account_name>\n"
        "  python ig_web_client.py setup  <anchor_account>   # add more accounts to session\n"
        "  python ig_web_client.py search <account_name> <query> [comment]"
    )
    if len(sys.argv) < 3:
        print(usage)
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd == "login":
            login(sys.argv[2])
        elif cmd == "setup":
            setup_multi_login(sys.argv[2])
        elif cmd == "search":
            if len(sys.argv) < 4:
                print(usage)
                sys.exit(1)
            comment_arg = sys.argv[4] if len(sys.argv) >= 5 else None
            search(sys.argv[2], sys.argv[3], comment=comment_arg)
        else:
            print(usage)
            sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
