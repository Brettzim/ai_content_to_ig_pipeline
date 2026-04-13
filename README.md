# AI Content to Instagram Pipeline

Generates AI-edited photos and videos from source images using the xAI Grok API, then posts them to Instagram via the Meta Graph API. Jobs can be driven from a Flask web UI or via JSON files in `ai/loads/`. Includes a Playwright-based auto-commenter that cycles through accounts using Instagram's native Switch-accounts feature.

## Pipeline

1. **Image edit** — xAI edits the source photo based on a `scene_prompt`
2. **Video generation** — xAI animates the edited image based on a `video_prompt`
3. **Instagram upload** — posts the result as a Reel (or photo) with a caption

## Setup

**1. Clone and create a virtual environment**
```bash
git clone <repo-url>
cd ai_content_to_ig_pipeline
python -m venv venv
```

**2. Install dependencies**
```bash
venv\Scripts\pip install -r requirements.txt
venv\Scripts\playwright install chromium
```

**3. Configure secrets**

Create a `.env` file in the project root:
```
XAI_API_KEY=your_xai_api_key
IG_ACCESS_TOKEN=your_meta_access_token
```

**4. Configure accounts**

Create `ai/personas/accounts.json`:
```json
[
  { "name": "account_name", "ig_user_id": "123456789" }
]
```

For the auto-commenter, also create `ai/personas/web_credentials.json` with per-account IG login credentials, and `ai/personas/auto_comment_config.json` with the comment bank and target mapping.

**5. Add source photos**

Drop source images into `ai/photos/` or into per-persona folders under `ai/personas/<model_name>/`.

## Running

**Web UI (preferred)**
```bash
venv\Scripts\python ui/web_app.py
# open http://localhost:5000
```
The UI exposes content generation plus a dedicated Auto-Comment page with a grid of personas × target accounts.

**CLI pipeline**
```bash
venv\Scripts\python python/meta_api/run.py                                    # run all loads
venv\Scripts\python python/meta_api/run.py --no-upload                        # generate only
venv\Scripts\python python/meta_api/run.py --loads-file ai/loads/example.json # single file
```

**Auto-commenter**
```bash
venv\Scripts\python python/web_crawler/auto_commenter.py
venv\Scripts\python python/web_crawler/auto_commenter.py --account valentina_vixen
venv\Scripts\python python/web_crawler/auto_commenter.py --dry-run
```
The browser session is always anchored on `valentina_vixen` — her Playwright `storage_state` must include the other accounts under IG's Switch-accounts roster.

## Load File Format

Create a `.json` file in `ai/loads/`:

```json
[
  {
    "photo": "filename.png",
    "account": "account_name",
    "post_type": "reel",
    "scene_prompt": "Place this woman in [outfit] at [setting]. Keep her face, hair, and body exactly the same.",
    "video_prompt": "Describe the motion, expression, and dialogue. Camera stays completely still.",
    "caption": "your caption here"
  }
]
```

| Field | Required | Description |
|---|---|---|
| `photo` | Yes | Filename in `ai/photos/` or persona-relative path like `personas/<name>/headshot.png` |
| `account` | Yes | Must match `name` in `accounts.json` |
| `post_type` | No | `"reel"` (default) or `"photo"` |
| `scene_prompt` | No | If omitted, the base photo is used directly |
| `video_prompt` | For reels | Describes video motion and dialogue |
| `caption` | Yes | Instagram caption |

## Project Structure

```
ai/                           all content & data
  personas/                   per-model folders + accounts.json, web_credentials.json, auto_comment_config.json
  prompt_engineering/         universal prompt rules (scene, video, creative direction, engagement)
  loads/                      CLI job JSON files
  photos/ edited_photos/ videos/

python/                       all Python modules (flat-import style)
  config.py                   shared settings; resolves paths from project root
  _pathsetup.py               sys.path shim for cross-folder flat imports
  grok/xai_client.py          xAI image edit + video generation
  meta_api/instagram_client.py
  meta_api/run.py             CLI pipeline runner
  web_crawler/ig_web_client.py
  web_crawler/auto_commenter.py
  web_crawler/sessions/       Playwright storage_state per account

ui/                           Flask frontend (web_app.py, templates/, static/)
logs/                         runtime logs
.env                          secrets (not committed)
```

## Notes

- The Instagram access token expires every ~60 days. Regenerate via Meta Graph API Explorer when posts start failing.
- All accounts share the single `IG_ACCESS_TOKEN` in `.env`; `accounts.json` holds only name + IG user ID.
- `edited_photos/` and `videos/` are auto-created on first run.
- Prompt generation pulls from `ai/prompt_engineering/` (universal rules) and `ai/personas/<name>/<name>.md` (per-model locked face, body, voice). Edit those files to change how prompts are generated.
