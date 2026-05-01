"""
Pipeline web interface.
Run: venv\\Scripts\\python ui/web_app.py
Open: http://localhost:5000
"""

import sys
from pathlib import Path

# Make python/ modules importable (flat imports: config, auto_commenter, etc.)
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "python"))
import _pathsetup  # noqa: F401  — injects grok/, meta_api/, web_crawler/ into sys.path

import json
import logging
import random
import secrets
import threading
import uuid
import requests
from flask import (
    Flask, abort, jsonify, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from werkzeug.security import check_password_hash

import config
import auto_commenter
from instagram_client import IGAccount, InstagramClient
from xai_client import XAIClient

USERS_FILE = config.AI_DIR / "users.json"

app = Flask(__name__)
app.secret_key = config.WEB_UI_SECRET or secrets.token_hex(32)
app.permanent_session_lifetime = 60 * 60 * 24 * 30  # 30 days
log = logging.getLogger(__name__)


# ── Per-user paths ────────────────────────────────────────────────────────────

def _load_users() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _find_user(username: str) -> dict | None:
    for u in _load_users():
        if u.get("username") == username:
            return u
    return None


def _user_dir(username: str | None = None) -> Path:
    u = username or session.get("username")
    if not u:
        abort(401)
    p = config.AI_DIR / "users" / u
    p.mkdir(parents=True, exist_ok=True)
    (p / "personas").mkdir(exist_ok=True)
    return p


def _user_personas_dir(username: str | None = None) -> Path:
    return _user_dir(username) / "personas"


def _user_accounts_file(username: str | None = None) -> Path:
    p = _user_dir(username) / "accounts.json"
    if not p.exists():
        p.write_text("[]", encoding="utf-8")
    return p


def _user_web_creds_file(username: str | None = None) -> Path:
    p = _user_dir(username) / "web_credentials.json"
    if not p.exists():
        p.write_text("[]", encoding="utf-8")
    return p


def _user_auto_comment_config(username: str | None = None) -> Path:
    p = _user_dir(username) / "auto_comment_config.json"
    if not p.exists():
        p.write_text(json.dumps({
            "comments": [], "accounts": [], "assignments": {},
            "delay_between_targets_s": [25, 70],
            "delay_between_accounts_s": [60, 180],
        }), encoding="utf-8")
    return p


def _user_sessions_dir(username: str | None = None) -> Path:
    u = username or session.get("username")
    if not u:
        abort(401)
    p = config.SESSIONS_DIR / u
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── Auth ──────────────────────────────────────────────────────────────────────

_PUBLIC_ENDPOINTS = {"login", "static"}


def _auth_enabled() -> bool:
    return bool(_load_users())


@app.before_request
def _require_login():
    if not _auth_enabled():
        return
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    if session.get("authed"):
        return
    if request.path.startswith("/api/") or request.path.startswith("/media/"):
        abort(401)
    return redirect(url_for("login", next=request.path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not _auth_enabled():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = _find_user(username)
        if user and check_password_hash(user.get("password_hash", ""), password):
            session.permanent = True
            session["authed"] = True
            session["username"] = username
            nxt = request.args.get("next") or url_for("index")
            if not nxt.startswith("/"):
                nxt = url_for("index")
            return redirect(nxt)
        error = "Incorrect username or password"
    return render_template("login.html", error=error), (401 if error else 200)


@app.route("/logout", methods=["POST", "GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))

# ── Shared dirs ───────────────────────────────────────────────────────────────

PROMPT_ENG_DIR = config.PROMPT_ENG_DIR

def _discover_personas(personas_dir: Path) -> dict:
    """Discover personas in the given dir (per-user)."""
    personas = {}
    if not personas_dir.exists():
        return personas
    for folder in sorted(personas_dir.iterdir()):
        if not folder.is_dir():
            continue
        headshot = folder / "headshot.png"
        if not headshot.exists():
            headshot = folder / "headshot.jpeg"
        if not headshot.exists():
            continue

        key = folder.name
        display_name = key.replace("_", " ").title()

        refs = [f"{key}/{headshot.name}"]
        for profile in ["left_profile.png", "right_profile.png"]:
            if (folder / profile).exists():
                refs.append(f"{key}/{profile}")

        personas[key] = {
            "display_name": display_name,
            "refs": refs,
        }
    return personas


def _load_persona_guide(personas_dir: Path, persona_key: str) -> str:
    path = personas_dir / persona_key / f"{persona_key}.md"
    if not path.exists():
        path = personas_dir / f"{persona_key}.md"
    if not path.exists():
        raise FileNotFoundError(f"Persona guide not found for: {persona_key}")
    return path.read_text(encoding="utf-8")


def _load_prompt_eng(filename: str) -> str:
    path = PROMPT_ENG_DIR / filename
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _load_workflow() -> str:
    return _load_prompt_eng("PROMPT_ENGINEERING_WORKFLOW.md")


def _load_engagement_guide() -> str:
    return _load_prompt_eng("ENGAGEMENT_GUIDE.md")


def _load_video_workflow() -> str:
    return _load_prompt_eng("VIDEO_PROMPT_ENGINEERING_WORKFLOW.md")


def _load_creative_direction() -> str:
    return _load_prompt_eng("CREATIVE_DIRECTION.md")


def _load_reel_instructions(reel_mode: str) -> str:
    filename = "REEL_SEDUCTIVE_LOOK.md" if reel_mode == "seductive_look" else "REEL_DANCE.md"
    return _load_prompt_eng(filename)


HISTORY_MAX = 10  # number of recent prompts to feed back to the LLM


def _load_history(personas_dir: Path, persona_key: str) -> list[str]:
    path = personas_dir / persona_key / "history.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[-HISTORY_MAX:]
    except (json.JSONDecodeError, KeyError):
        return []


def _save_history(personas_dir: Path, persona_key: str, scene_prompt: str):
    path = personas_dir / persona_key / "history.json"
    history = _load_history(personas_dir, persona_key)
    history.append(scene_prompt)
    history = history[-HISTORY_MAX:]
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def _generate_prompts_ai(personas_dir: Path, persona_key: str, post_type: str) -> dict:
    workflow = _load_workflow()
    guide = _load_persona_guide(personas_dir, persona_key)
    engagement = _load_engagement_guide()
    creative_direction = _load_creative_direction()
    video_workflow = _load_video_workflow() if post_type == "reel" else ""
    personas = _discover_personas(personas_dir)
    p = personas[persona_key]
    display_name = p["display_name"]
    history = _load_history(personas_dir, persona_key)

    video_field = '"video_prompt": "...",' if post_type == "reel" else ""

    video_section = f"""
=== VIDEO PROMPT ENGINEERING WORKFLOW ===
{video_workflow}
""" if post_type == "reel" else ""

    system_msg = f"""You are a professional Instagram content prompt writer for AI image/video generation.

You have the following reference documents. Each document has a specific authority domain — follow it exactly:

=== PROMPT ENGINEERING WORKFLOW ===
{workflow}

=== ENGAGEMENT GUIDE ===
{engagement}
{video_section}
=== CREATIVE DIRECTION ===
{creative_direction}

=== MODEL GUIDE ===
{guide}

## Document Authority Rules

**PROMPT ENGINEERING WORKFLOW** — sole authority on scene prompt structure and word selection.
Follow the 5-part structure (environment → film layer → camera angle → subject → lighting) and the forbidden/replacement word list exactly.

**ENGAGEMENT GUIDE** — sole authority on caption FORMAT, RULES, and STRUCTURE.
Use the caption writing rules from this guide for every caption: hook first, 100–150 chars for photos (shorter for reels), no photo description, 1–2 emojis max at end of line, no hashtags in caption.
Use the Hook Formulas table to select the right hook type for the scene.
The caption examples in the Model Guide are illustrative of voice and tone ONLY — they do not override the Engagement Guide's structural rules.

**CREATIVE DIRECTION** — sole authority on how to match poses, camera angles, and facial expressions to settings and activities. Follow this guide to build a believable, varied scene.

**MODEL GUIDE** — sole authority on: body specs, approved locations and scenarios, wardrobe, voice/tone, camera style, and the character's emoji palette.
When writing the caption, use this guide for: what she would say, her personality register, and which 1–2 emojis from her palette fit the hook. Structure and length come from the Engagement Guide.

**VIDEO PROMPT ENGINEERING WORKFLOW** (reels only) — sole authority on beat structure, timing, motion rules, dialogue timing, and character motion profiles.

## CRITICAL: Creative Freedom

You are the creative director. Every generation must be completely unique.
Read the Model Guide carefully — it defines this character's personality, hobbies, wardrobe, and camera style.
Read the Creative Direction guide — it tells you how to connect poses, expressions, and camera angles to make a believable scene.
Be inventive. Think candid, spontaneous, real. Never default to generic "standing and looking at camera."
Stay within the character's aesthetic but invent something new every time."""

    history_block = ""
    if history:
        numbered = "\n".join(f"{i+1}. {p}" for i, p in enumerate(history))
        history_block = f"""
RECENTLY GENERATED — DO NOT REPEAT:
The following scene prompts were recently generated for this character. You MUST create something meaningfully different — different location, different pose, different outfit, different camera angle. Do not reuse the same combination of elements.

{numbered}
"""

    if post_type == "reel":
        reel_mode = random.choices(["seductive_look", "dance"], weights=[80, 20], k=1)[0]
        caption_length = "Max 100 characters — shorter is better for reels"

        scene_instructions = _load_reel_instructions(reel_mode)
    else:
        reel_mode = None
        scene_instructions = "- No video prompt needed"
        caption_length = "100–150 characters max"

    user_msg = f"""Generate one {post_type} post for {display_name}.
{history_block}
IMPORTANT: The image will be generated using image editing with a reference photo of this character's face. The reference photo provides ONLY the face — your prompt controls everything else (body, pose, outfit, setting, camera, expression).

Scene prompt requirements:
- Start the prompt with: "Using this woman's exact face, generate a photo."
{"- This is a REEL — the scene prompt creates the starting frame of the video. Follow the reel-specific instructions below carefully." if post_type == "reel" else "- Follow the Creative Direction guide steps: first choose a post type (Step 1), then choose a camera and quality (Step 2) that fits the post type and narrative. Don't default to the same camera every time."}
- Pick a location from the Model Guide's Settings & Locations that fits the character.
- Use the Model Guide for body specs, wardrobe aesthetic, and camera style preferences.
- Include the LOCKED body block from the model guide.
- Describe the hairstyle for this specific shot (vary it — ponytail, loose, bun, braids, half-up, etc.)
- Do NOT include the face description block — the reference images handle the face.
- Follow the structure: reference instruction → setting → body + pose + outfit + hairstyle → camera angle → lighting
- Scene prompt: 60–80 words
{scene_instructions}

Caption requirements (follow the Engagement Guide — these rules are non-negotiable):
- Hook first — the first line must work standalone before the "more" cutoff
- {caption_length}
- Do NOT describe the photo or explain the vibe — react to it obliquely, reference it sideways, or ignore it
- Choose a hook formula from the Engagement Guide that fits the scene (declarative dismissal, double meaning, understatement, etc.)
- Write in this character's voice using her personality register from the model guide
- 1–2 emojis maximum, from her emoji palette, at the end of the line only
- No hashtags in the caption

Return ONLY valid JSON (no markdown, no explanation):
{{
  "scene_prompt": "...",
  {video_field}
  "caption": "..."
}}"""

    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {config.XAI_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "grok-3-latest",
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 1.0,
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    result = json.loads(content.strip())
    _save_history(personas_dir, persona_key, result["scene_prompt"])
    return result


# ── Job store ─────────────────────────────────────────────────────────────────

_jobs: dict[str, dict] = {}


def _run_generate(job_id: str):
    job = _jobs[job_id]
    try:
        xai = XAIClient()
        personas_dir = _user_personas_dir(job["username"])
        p = _discover_personas(personas_dir)[job["persona"]]

        # Use headshot as reference for face consistency
        headshot = personas_dir / p["refs"][0]

        job["status"] = "editing_image"
        result = xai.edit_image(
            image_paths=[headshot],
            prompt=job["prompts"]["scene_prompt"],
            save_path=config.EDITED_PHOTOS_DIR / f"{job_id}.png",
        )
        job["edited_image"] = f"/media/edited/{job_id}.png"
        job["image_url"] = result["image_url"]

        if job["post_type"] == "reel":
            job["status"] = "generating_video"
            video_result = xai.process_photo(
                image_path=result["path"],
                prompt=job["prompts"]["video_prompt"],
                save_name=job_id,
            )
            job["video_url"] = video_result["video_url"]
            job["video_local"] = str(video_result["path"])
            job["media_preview"] = f"/media/video/{job_id}.mp4"

        job["status"] = "ready"
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        log.exception(f"generate job {job_id} failed")


def _run_post(job_id: str):
    job = _jobs[job_id]
    try:
        job["post_status"] = "posting"
        with open(_user_accounts_file(job["username"]), encoding="utf-8") as f:
            accounts = {a["name"]: a for a in json.load(f)}

        raw = accounts[job["persona"]]
        client = InstagramClient(
            IGAccount(name=raw["name"], ig_user_id=raw["ig_user_id"]),
            config.IG_ACCESS_TOKEN,
        )

        if job["post_type"] == "reel":
            media_id = client.post_reel(video_url=job["video_url"], caption=job["prompts"]["caption"])
        else:
            media_id = client.post_photo(image_url=job["image_url"], caption=job["prompts"]["caption"])

        job["post_status"] = "posted"
        job["media_id"] = media_id
    except Exception as e:
        job["post_status"] = "error"
        job["post_error"] = str(e)
        log.exception(f"post job {job_id} failed")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/auto-comment")
def auto_comment_page():
    return render_template("auto_comment.html")


# ── Auto-comment API ──────────────────────────────────────────────────────────

_auto_jobs: dict[str, dict] = {}


class _ListLogHandler(logging.Handler):
    def __init__(self, buf: list):
        super().__init__()
        self.buf = buf

    def emit(self, record):
        try:
            self.buf.append(self.format(record))
            if len(self.buf) > 500:
                del self.buf[:len(self.buf) - 500]
        except Exception:
            pass


def _load_auto_config(path: Path) -> dict:
    default = {
        "comments": [], "accounts": [], "assignments": {}, "groups": [],
        "delay_between_targets_s": [25, 70],
        "delay_between_accounts_s": [60, 180],
    }
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    if isinstance(cfg.get("accounts"), dict):
        legacy = cfg.pop("accounts")
        cfg.setdefault("assignments", legacy)
        seen, flat = set(), []
        for ts in legacy.values():
            for t in ts:
                if t not in seen:
                    seen.add(t); flat.append(t)
        cfg.setdefault("accounts", flat)
    # Migrate legacy assignments → groups: bucket models by their target set so
    # users with per-model customization don't lose granularity.
    if not cfg.get("groups") and cfg.get("assignments"):
        buckets: dict[tuple, list[str]] = {}
        for model, targets in cfg["assignments"].items():
            if not targets:
                continue
            buckets.setdefault(tuple(sorted(targets)), []).append(model)
        groups = []
        for i, (targets_key, models) in enumerate(buckets.items(), 1):
            groups.append({
                "name": "Default" if len(buckets) == 1 else f"Group {i}",
                "models": sorted(models),
                "targets": list(targets_key),
            })
        cfg["groups"] = groups
    for k, v in default.items():
        cfg.setdefault(k, v)
    return cfg


def _load_web_credential_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        creds = json.load(f)
    return [c["name"] for c in creds if c.get("name")]


def _save_auto_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@app.route("/api/auto-comment/config", methods=["GET", "POST"])
def api_auto_comment_config():
    cfg_path = _user_auto_comment_config()
    if request.method == "GET":
        return jsonify(_load_auto_config(cfg_path))
    try:
        data = request.json or {}
        # Sanitize groups
        groups: list[dict] = []
        all_targets: list[str] = []
        seen_targets: set[str] = set()
        for g in (data.get("groups") or []):
            name = (g.get("name") or "").strip() or "Untitled"
            models = list(dict.fromkeys(
                m for m in (g.get("models") or []) if isinstance(m, str) and m
            ))
            targets = list(dict.fromkeys(
                t.strip().lstrip("@")
                for t in (g.get("targets") or [])
                if isinstance(t, str) and t.strip()
            ))
            groups.append({"name": name, "models": models, "targets": targets})
            for t in targets:
                if t not in seen_targets:
                    seen_targets.add(t)
                    all_targets.append(t)

        # Derive assignments + accounts for backend compat (auto_commenter reads these)
        assignments: dict[str, list[str]] = {}
        for g in groups:
            for m in g["models"]:
                bucket = assignments.setdefault(m, [])
                for t in g["targets"]:
                    if t not in bucket:
                        bucket.append(t)

        cleaned = {
            "comments": [c for c in (data.get("comments") or []) if c.strip()],
            "groups": groups,
            "accounts": all_targets,
            "assignments": assignments,
            "delay_between_targets_s": data.get("delay_between_targets_s", [25, 70]),
            "delay_between_accounts_s": data.get("delay_between_accounts_s", [60, 180]),
        }
        _save_auto_config(cfg_path, cleaned)
        return jsonify({"ok": True})
    except Exception as e:
        log.exception("save auto-comment config failed")
        return jsonify({"ok": False, "error": str(e)}), 500


_auto_commenter_lock = threading.Lock()


def _run_auto_commenter(job_id: str, dry_run: bool, username: str):
    job = _auto_jobs[job_id]
    cfg_path = _user_auto_comment_config(username)
    creds_file = _user_web_creds_file(username)

    logger = logging.getLogger("auto_commenter")
    web_logger = logging.getLogger("ig_web_client")
    handler = _ListLogHandler(job["log"])
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    web_logger.addHandler(handler)
    try:
        with _auto_commenter_lock:
            # Resolve sessions_dir inside the lock — config.SESSIONS_DIR is
            # temporarily mutated below and we need the original parent here.
            old_creds = config.WEB_CREDENTIALS_FILE
            old_sessions = config.SESSIONS_DIR
            sessions_dir = old_sessions / username
            sessions_dir.mkdir(parents=True, exist_ok=True)
            config.WEB_CREDENTIALS_FILE = creds_file
            config.SESSIONS_DIR = sessions_dir
            try:
                job["status"] = "running"
                results = auto_commenter.run(cfg_path, dry_run=dry_run)
                job["results"] = results
                job["status"] = "done"
            finally:
                config.WEB_CREDENTIALS_FILE = old_creds
                config.SESSIONS_DIR = old_sessions
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        log.exception(f"auto-comment job {job_id} failed")
    finally:
        logger.removeHandler(handler)
        web_logger.removeHandler(handler)


@app.route("/api/auto-comment/run", methods=["POST"])
def api_auto_comment_run():
    try:
        data = request.json or {}
        dry_run = bool(data.get("dry_run"))
        username = session.get("username") or ""
        job_id = uuid.uuid4().hex[:8]
        _auto_jobs[job_id] = {
            "id": job_id, "status": "starting",
            "results": [], "log": [], "dry_run": dry_run,
            "username": username,
        }
        threading.Thread(
            target=_run_auto_commenter, args=(job_id, dry_run, username), daemon=True,
        ).start()
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/auto-comment/job/<job_id>")
def api_auto_comment_job(job_id):
    job = _auto_jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/api/web-credentials", methods=["GET", "POST"])
def api_web_credentials():
    creds_file = _user_web_creds_file()
    if request.method == "GET":
        return jsonify({"names": _load_web_credential_names(creds_file)})

    data = request.json or {}
    ig_username = (data.get("username") or "").strip().lstrip("@")
    ig_password = data.get("password") or ""
    name = (data.get("name") or "").strip().lower()
    if not name:
        name = "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in ig_username.lower())

    if not ig_username or not ig_password:
        return jsonify({"ok": False, "error": "Username and password are required"}), 400
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        return jsonify({"ok": False, "error": "Name must contain only letters, numbers, and underscores"}), 400

    with open(creds_file, encoding="utf-8") as f:
        creds = json.load(f)
    if any(c.get("name") == name for c in creds):
        return jsonify({"ok": False, "error": f"Account '{name}' already exists"}), 409

    creds.append({"name": name, "username": ig_username, "password": ig_password})
    creds_file.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    return jsonify({"ok": True, "name": name})


@app.route("/api/personas")
def api_personas():
    personas = _discover_personas(_user_personas_dir())
    return jsonify({
        k: {"display_name": v["display_name"]}
        for k, v in personas.items()
    })


@app.route("/api/generate-prompts", methods=["POST"])
def api_generate_prompts():
    data = request.json
    try:
        prompts = _generate_prompts_ai(_user_personas_dir(), data["persona"], data["post_type"])
        return jsonify({"ok": True, "prompts": prompts})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/generate-content", methods=["POST"])
def api_generate_content():
    data = request.json
    job_id = uuid.uuid4().hex[:8]
    _jobs[job_id] = {
        "id": job_id,
        "persona": data["persona"],
        "post_type": data["post_type"],
        "prompts": data["prompts"],
        "status": "starting",
        "post_status": None,
        "username": session.get("username") or "",
    }
    threading.Thread(target=_run_generate, args=(job_id,), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/clear-history", methods=["POST"])
def api_clear_history():
    try:
        personas_dir = _user_personas_dir()
        for persona_key in _discover_personas(personas_dir):
            path = personas_dir / persona_key / "history.json"
            if path.exists():
                path.unlink()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/job/<job_id>")
def api_job(job_id):
    job = _jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/api/post", methods=["POST"])
def api_post():
    job_id = request.json["job_id"]
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    threading.Thread(target=_run_post, args=(job_id,), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/dashboard")
def api_dashboard():
    try:
        with open(_user_accounts_file(), encoding="utf-8") as f:
            accounts = json.load(f)
        personas = _discover_personas(_user_personas_dir())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = {}
    for acct in accounts:
        name = acct["name"]
        uid = acct.get("ig_user_id", "")
        if not uid:
            continue
        try:
            resp = requests.get(
                f"https://graph.facebook.com/v21.0/{uid}/media",
                params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count",
                    "limit": 12,
                    "access_token": config.IG_ACCESS_TOKEN,
                },
                timeout=30,
            )
            resp.raise_for_status()
            posts = resp.json().get("data", [])
        except Exception as e:
            posts = []
            log.warning(f"Dashboard fetch failed for {name}: {e}")

        try:
            dm_resp = requests.get(
                f"https://graph.facebook.com/v21.0/{uid}/conversations",
                params={
                    "fields": "id,updated_time,messages{message,from,created_time}",
                    "platform": "instagram",
                    "access_token": config.IG_ACCESS_TOKEN,
                },
                timeout=20,
            )
            dm_resp.raise_for_status()
            conversations = dm_resp.json().get("data", [])
        except Exception as e:
            conversations = []
            log.warning(f"DM fetch failed for {name}: {e}")

        result[name] = {
            "display_name": personas.get(name, {}).get("display_name", name),
            "posts": posts,
            "total_likes": sum(p.get("like_count", 0) for p in posts),
            "total_comments": sum(p.get("comments_count", 0) for p in posts),
            "post_count": len(posts),
            "conversations": conversations,
            "dm_count": len(conversations),
        }

    return jsonify(result)


@app.route("/api/reply", methods=["POST"])
def api_reply():
    data = request.json
    comment_id = data["comment_id"]
    message = data["message"]
    account_name = data["account"]
    try:
        with open(_user_accounts_file(), encoding="utf-8") as f:
            accounts = {a["name"]: a for a in json.load(f)}
        uid = accounts[account_name]["ig_user_id"]
        resp = requests.post(
            f"https://graph.facebook.com/v21.0/{comment_id}/replies",
            params={"access_token": config.IG_ACCESS_TOKEN},
            json={"message": message, "ig_user_id": uid},
            timeout=20,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "id": resp.json().get("id")})
    except Exception as e:
        try:
            detail = resp.json().get("error", {}).get("message", str(e))
        except Exception:
            detail = str(e)
        return jsonify({"ok": False, "error": detail}), 500


@app.route("/api/comments/<media_id>")
def api_comments(media_id):
    try:
        resp = requests.get(
            f"https://graph.facebook.com/v21.0/{media_id}/comments",
            params={
                "fields": "text,username,timestamp,like_count",
                "limit": 50,
                "access_token": config.IG_ACCESS_TOKEN,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "comments": resp.json().get("data", [])})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/media/edited/<filename>")
def serve_edited(filename):
    return send_from_directory(config.EDITED_PHOTOS_DIR, filename)


@app.route("/media/video/<filename>")
def serve_video(filename):
    return send_from_directory(config.VIDEOS_DIR, filename)


@app.route("/media/headshot/<persona_key>")
def serve_headshot(persona_key):
    folder = _user_personas_dir() / persona_key
    for ext in ("png", "jpeg", "jpg"):
        headshot = folder / f"headshot.{ext}"
        if headshot.exists():
            return send_from_directory(folder, headshot.name)
    abort(404)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config.EDITED_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    config.VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
