"""
Grok Imagine -> Instagram Reels Pipeline.

USAGE EXAMPLES
--------------
# Run all .json files in loads/ folder (generate + upload)
python run.py

# Generate only, no upload
python run.py --no-upload

# Run a single load file
python run.py --loads-file loads/monday.json

# Control parallelism (default: 3 concurrent xAI jobs)
python run.py --parallel 5

ACCOUNTS FILE (accounts.json)
------------------------------
[
  {
    "name": "personality_one",
    "ig_user_id": "123456789",
    "access_token": "EAAxxxxxxx"
  }
]

LOADS FOLDER (loads/)
---------------------
Drop any number of .json files here. Each file is a list of jobs:

[
  {
    "photo": "personas/valentina_vixen/headshot.png",
    "account": "personality_one",
    "scene_prompt": "Place this woman at [setting] wearing [outfit]. Keep her face, hair, and body exactly the same.",
    "video_prompt": "She turns toward the camera with a slow smile. She mouths 'you know you want to'. Camera stays completely still.",
    "caption": "Good morning ☀️ #ai #model"
  }
]

scene_prompt is optional. If omitted, the base photo is used directly for video generation.
"""

import argparse
import json
import logging
import sys
import time
import concurrent.futures
from pathlib import Path

from xai_client import XAIClient
from instagram_client import InstagramClient, IGAccount
import config

DEFAULT_PROMPT = (
    "The subject in this exact scene with the same outfit and setting "
    "slowly moves naturally. Subtle body movement, gentle breathing, "
    "slight head turn. Camera stays completely still. "
    "Preserve the exact appearance, clothing, and environment from the image."
)


# ------------------------------------------------------------------ #
#  Setup                                                              #
# ------------------------------------------------------------------ #

def setup_logging():
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    import io
    stream_handler = logging.StreamHandler(
        io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    )
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            stream_handler,
            logging.FileHandler(config.LOGS_DIR / "pipeline.log", encoding="utf-8"),
        ],
    )


# ------------------------------------------------------------------ #
#  Accounts                                                           #
# ------------------------------------------------------------------ #

def load_accounts() -> dict:
    """Load accounts from accounts.json. Returns a dict keyed by name."""
    if not config.ACCOUNTS_FILE.exists():
        raise FileNotFoundError(
            f"accounts.json not found at {config.ACCOUNTS_FILE}"
        )
    with open(config.ACCOUNTS_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {a["name"]: a for a in raw}


def make_client(raw: dict) -> InstagramClient:
    account = IGAccount(name=raw["name"], ig_user_id=raw["ig_user_id"])
    return InstagramClient(account, config.IG_ACCESS_TOKEN)


# ------------------------------------------------------------------ #
#  Jobs file                                                          #
# ------------------------------------------------------------------ #

def load_jobs_file(path: Path, accounts_map: dict, upload: bool) -> list[tuple]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    jobs = []
    for entry in raw:
        photo_val = entry["photo"]
        # Support persona-relative paths (e.g. "personas/rachel_key/headshot.png")
        photo_path = Path(photo_val)
        if photo_path.is_absolute():
            photo = photo_path.resolve()
        elif photo_val.startswith("personas/"):
            photo = (config.BASE_DIR / photo_val).resolve()
        else:
            photo = (config.PHOTOS_DIR / photo_val).resolve()
        # scene_prompt is optional — if absent, base photo is used directly
        scene_prompt = entry.get("scene_prompt")
        video_prompt = entry.get("video_prompt") or entry.get("prompt") or DEFAULT_PROMPT
        caption = entry.get("caption", "")
        post_type = entry.get("post_type", "reel")
        if post_type not in ("reel", "photo"):
            raise ValueError(f"Invalid post_type '{post_type}' — must be 'reel' or 'photo'")
        clients = []
        if upload:
            account_name = entry.get("account")
            if account_name and account_name in accounts_map:
                clients = [make_client(accounts_map[account_name])]
            elif account_name:
                raise ValueError(f"Account '{account_name}' not found in accounts.json")
        jobs.append((photo, scene_prompt, video_prompt, caption, post_type, clients))
    return jobs


def load_all_jobs(loads_dir: Path, accounts_map: dict, upload: bool) -> list[tuple]:
    """Load all .json files from the loads folder."""
    job_files = sorted(loads_dir.glob("*.json"))
    if not job_files:
        raise FileNotFoundError(f"No .json files found in {loads_dir}/")
    jobs = []
    for jf in job_files:
        jobs.extend(load_jobs_file(jf, accounts_map, upload))
    return jobs


def _client_name(client) -> str:
    return client.account.name


# ------------------------------------------------------------------ #
#  Core job: generate one video, then post to all target accounts     #
# ------------------------------------------------------------------ #

def process_job(
    xai_client: XAIClient,
    ig_clients: list[InstagramClient],
    photo: Path,
    scene_prompt: str,
    video_prompt: str,
    caption: str,
    post_type: str = "reel",
) -> dict:
    logger = logging.getLogger("pipeline")
    ig_posts: dict[str, str] = {}
    video_path = None
    video_url = None
    status = "ok"

    try:
        # ── Step 1: Edit image (outfit + setting) ─────────────────────
        if scene_prompt:
            edited_save = config.EDITED_PHOTOS_DIR / photo.name
            edited = xai_client.edit_image(photo, scene_prompt, edited_save)
            source_photo = edited["path"]
            source_url   = edited["image_url"]
            logger.info(f"[{photo.name}] Image edited -> {source_photo.name}")
        else:
            source_photo = photo
            source_url   = None

        if post_type == "photo":
            # ── Step 2 (photo): Upload edited image directly ──────────
            for client in ig_clients:
                name = _client_name(client)
                try:
                    if not source_url:
                        raise ValueError("API photo post requires a scene_prompt to generate a public URL")
                    media_id = client.post_photo(image_url=source_url, caption=caption)
                    ig_posts[name] = media_id
                    logger.info(f"[{photo.name}] Photo posted to {name} -> {media_id}")
                except Exception as e:
                    err = str(e)
                    ig_posts[name] = f"FAIL: {err}"
                    logger.error(f"[{photo.name}] IG photo post failed for {name}: {err}")
                finally:
                    time.sleep(config.IG_POST_DELAY)

        else:
            # ── Step 2 (reel): Generate video via xAI ─────────────────
            gen = xai_client.process_photo(source_photo, video_prompt)
            video_path = gen["path"]
            video_url  = gen["video_url"]
            logger.info(f"[{photo.name}] Video ready -> {gen['path'].name}")

            # ── Step 3 (reel): Upload to each Instagram account ───────
            for client in ig_clients:
                name = _client_name(client)
                try:
                    media_id = client.post_reel(video_url=video_url, caption=caption)
                    ig_posts[name] = media_id
                    logger.info(f"[{photo.name}] Reel posted to {name} -> {media_id}")
                except Exception as e:
                    err = str(e)
                    ig_posts[name] = f"FAIL: {err}"
                    logger.error(f"[{photo.name}] IG reel post failed for {name}: {err}")
                finally:
                    time.sleep(config.IG_POST_DELAY)

    except Exception as e:
        status = f"fail: {e}"
        logger.error(f"[{photo.name}] Pipeline failed: {e}", exc_info=True)

    return {
        "photo": photo,
        "video_path": video_path,
        "video_url": video_url,
        "ig_posts": ig_posts,
        "status": status,
    }


# ------------------------------------------------------------------ #
#  Main                                                               #
# ------------------------------------------------------------------ #

def main():
    setup_logging()
    logger = logging.getLogger("pipeline")

    parser = argparse.ArgumentParser(
        description="Grok Imagine -> Instagram Reels Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--loads-dir", default=None, help="Folder of .json load files (default: loads/)")
    parser.add_argument("--loads-file", default=None, help="Run a single .json load file")
    parser.add_argument("--no-upload", action="store_true", help="Generate videos without uploading")
    parser.add_argument("--duration",   type=int, help="Video duration 1-15s")
    parser.add_argument("--aspect",     help="Aspect ratio (9:16, 16:9, 1:1)")
    parser.add_argument("--resolution", help="Resolution (720p or 480p)")
    parser.add_argument("--parallel", type=int, default=3, help="Concurrent xAI jobs (default: 3)")

    args = parser.parse_args()
    upload = not args.no_upload

    if args.duration:   config.VIDEO_DURATION     = args.duration
    if args.aspect:     config.VIDEO_ASPECT_RATIO = args.aspect
    if args.resolution: config.VIDEO_RESOLUTION   = args.resolution

    # ── Load accounts ─────────────────────────────────────────────────
    accounts_map = load_accounts() if upload else {}

    # ── Load jobs ─────────────────────────────────────────────────────
    if args.loads_file:
        jobs = load_jobs_file(Path(args.loads_file), accounts_map, upload)
    else:
        loads_dir = Path(args.loads_dir) if args.loads_dir else config.LOADS_DIR
        loads_dir.mkdir(parents=True, exist_ok=True)
        jobs = load_all_jobs(loads_dir, accounts_map, upload)

    if not jobs:
        logger.error("No jobs found.")
        sys.exit(1)

    logger.info(f"Jobs:       {len(jobs)}")
    logger.info(f"Parallel:   {args.parallel}")
    logger.info(f"Settings:   {config.VIDEO_DURATION}s | {config.VIDEO_ASPECT_RATIO} | {config.VIDEO_RESOLUTION}")
    logger.info(f"Upload:     {'YES' if upload else 'No'}")
    logger.info("")
    for i, (photo, scene_prompt, video_prompt, caption, post_type, clients) in enumerate(jobs, 1):
        logger.info(f"  [{i}] {photo.name} ({post_type})")
        if scene_prompt:
            logger.info(f"      Scene:  {scene_prompt[:120]}...")
        logger.info(f"      Video:  {video_prompt[:120]}...")
        logger.info(f"      Caption: {caption}")

    # ── Run jobs ──────────────────────────────────────────────────────
    xai_client = XAIClient()
    results = []

    def run_job(job: tuple) -> dict:
        photo, scene_prompt, video_prompt, caption, post_type, clients = job
        return process_job(xai_client, clients, photo, scene_prompt, video_prompt, caption, post_type)

    if args.parallel > 1 and len(jobs) > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futures = {pool.submit(lambda j=job: run_job(j)): job[0] for job in jobs}  # type: ignore[arg-type]
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
    else:
        for i, job in enumerate(jobs, 1):
            logger.info(f"\n[{i}/{len(jobs)}] {job[0].name}")
            results.append(run_job(job))

    # ── Final summary ─────────────────────────────────────────────────
    ok = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"\n{'='*50}")
    logger.info(f"Done: {ok}/{len(results)} videos generated successfully")
    logger.info(f"{'='*50}")

    for r in results:
        tag      = "OK  " if r["status"] == "ok" else "FAIL"
        vid_name = r["video_path"].name if r["video_path"] else "-"
        ig_status = ""
        if r["ig_posts"]:
            parts = [f"{acc}: {val}" for acc, val in r["ig_posts"].items()]
            ig_status = " | IG -> " + ", ".join(parts)
        logger.info(f"  [{tag}] {r['photo'].name} -> {vid_name}{ig_status}")


if __name__ == "__main__":
    main()
