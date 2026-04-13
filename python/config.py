import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Project layout (after 2026-04-12 reorg):
#   <root>/ai/      → personas, prompt_engineering, loads, photos, edited_photos, videos
#   <root>/python/  → config.py + grok/, meta_api/, web_crawler/
#   <root>/ui/      → web_app.py, templates/, static/
#   <root>/logs/    → runtime logs
BASE_DIR = Path(__file__).resolve().parent.parent
AI_DIR = BASE_DIR / "ai"

# ------------------------------------------------------------------ #
#  xAI API                                                            #
# ------------------------------------------------------------------ #
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_BASE_URL = "https://api.x.ai/v1"

# Video generation settings
VIDEO_MODEL = "grok-imagine-video"
VIDEO_DURATION = int(os.getenv("VIDEO_DURATION", "10"))       # 1-15 seconds
VIDEO_ASPECT_RATIO = os.getenv("VIDEO_ASPECT_RATIO", "9:16")  # 9:16 for IG Reels
VIDEO_RESOLUTION = os.getenv("VIDEO_RESOLUTION", "480p")      # 720p or 480p

# Polling (xAI)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))         # seconds between status checks
POLL_TIMEOUT  = int(os.getenv("POLL_TIMEOUT", "300"))         # max wait for video generation

# ------------------------------------------------------------------ #
#  Instagram / Meta Graph API                                         #
# ------------------------------------------------------------------ #
ACCOUNTS_FILE = Path(os.getenv("ACCOUNTS_FILE", AI_DIR / "personas" / "accounts.json"))
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# Post rate-limit safety delay between accounts (seconds)
IG_POST_DELAY = int(os.getenv("IG_POST_DELAY", "10"))

# ------------------------------------------------------------------ #
#  Instagram Web Client (Playwright / stealth)                        #
# ------------------------------------------------------------------ #
WEB_CREDENTIALS_FILE = Path(os.getenv("WEB_CREDENTIALS_FILE", AI_DIR / "personas" / "web_credentials.json"))
SESSIONS_DIR         = Path(os.getenv("SESSIONS_DIR",         BASE_DIR / "python" / "web_crawler" / "sessions"))
WEB_HEADLESS         = os.getenv("WEB_HEADLESS", "false").lower() == "true"

# ------------------------------------------------------------------ #
#  Content directories                                                #
# ------------------------------------------------------------------ #
PERSONAS_DIR      = Path(os.getenv("PERSONAS_DIR",      AI_DIR / "personas"))
PROMPT_ENG_DIR    = Path(os.getenv("PROMPT_ENG_DIR",    AI_DIR / "prompt_engineering"))
PHOTOS_DIR        = Path(os.getenv("PHOTOS_DIR",        AI_DIR / "photos"))
EDITED_PHOTOS_DIR = Path(os.getenv("EDITED_PHOTOS_DIR", AI_DIR / "edited_photos"))
VIDEOS_DIR        = Path(os.getenv("VIDEOS_DIR",        AI_DIR / "videos"))
LOADS_DIR         = Path(os.getenv("LOADS_DIR",         AI_DIR / "loads"))
LOGS_DIR          = Path(os.getenv("LOGS_DIR",          BASE_DIR / "logs"))
