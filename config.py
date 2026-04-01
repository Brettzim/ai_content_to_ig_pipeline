import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent

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
# accounts.json path — each entry: {name, ig_user_id}
ACCOUNTS_FILE = Path(os.getenv("ACCOUNTS_FILE", BASE_DIR / "personas" / "accounts.json"))
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

# Post rate-limit safety delay between accounts (seconds)
IG_POST_DELAY = int(os.getenv("IG_POST_DELAY", "10"))

# ------------------------------------------------------------------ #
#  Directories                                                        #
# ------------------------------------------------------------------ #
PHOTOS_DIR        = Path(os.getenv("PHOTOS_DIR",        BASE_DIR / "photos"))
EDITED_PHOTOS_DIR = Path(os.getenv("EDITED_PHOTOS_DIR", BASE_DIR / "edited_photos"))
VIDEOS_DIR        = Path(os.getenv("VIDEOS_DIR",        BASE_DIR / "videos"))
LOGS_DIR          = Path(os.getenv("LOGS_DIR",          BASE_DIR / "logs"))
LOADS_DIR         = Path(os.getenv("LOADS_DIR",         BASE_DIR / "loads"))
