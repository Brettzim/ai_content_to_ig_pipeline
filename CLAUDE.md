# Grok Pipeline — Claude Instructions

## What This Project Does
Generates AI images and videos from photos using the xAI Grok API, then posts them to Instagram via the Meta Graph API. Jobs are defined in JSON files in `loads/` or triggered via the web UI.

## How to Run

```bash
# Web UI (preferred)
venv\Scripts\python ui/web_app.py
# Open http://localhost:5000

# CLI — run all loads
venv\Scripts\python python/meta_api/run.py

# CLI — single file, no upload
venv\Scripts\python python/meta_api/run.py --loads-file ai/loads/valentina_vixen.json --no-upload

# Auto-commenter (web crawler)
venv\Scripts\python python/web_crawler/auto_commenter.py
```

## Project Structure

```
ai/                           — all content & data
  personas/                   — per-model folders (profile .md, refs, history)
                                plus accounts.json, web_credentials.json, auto_comment_config.json
  prompt_engineering/         — universal prompt rules
  loads/                      — CLI job JSON files
  photos/ edited_photos/ videos/

python/                       — all Python modules (flat-import style)
  config.py                   — shared settings; resolves paths from project root
  _pathsetup.py               — shim that puts grok/, meta_api/, web_crawler/ on sys.path
  grok/xai_client.py
  meta_api/instagram_client.py
  meta_api/run.py             — CLI pipeline runner
  web_crawler/ig_web_client.py
  web_crawler/auto_commenter.py
  web_crawler/sessions/       — Playwright storage_state per account

ui/                           — Flask frontend
  web_app.py  templates/  static/

logs/                         — runtime logs
.env                          — secrets: XAI_API_KEY, IG_ACCESS_TOKEN
```

Each entry script prepends `python/` to `sys.path` and imports `_pathsetup`,
which makes flat imports (`import config`, `from xai_client import ...`,
`import ig_web_client as web`) work regardless of folder.

## Content Generation

Prompt generation is driven by files in two directories:

**`prompt_engineering/`** — universal rules:
- `PROMPT_ENGINEERING_WORKFLOW.md` — structure rules for scene prompts
- `VIDEO_PROMPT_ENGINEERING_WORKFLOW.md` — beat structure, motion rules for video
- `CREATIVE_DIRECTION.md` — post types, camera selection, pose/expression rules
- `ENGAGEMENT_GUIDE.md` — caption rules, posting strategy, aesthetic guidelines
- `REEL_SEDUCTIVE_LOOK.md` — selfie-angle seductive reel instructions
- `REEL_DANCE.md` — TikTok-style dance reel instructions

**`personas/<model_name>/`** — per-model:
- `<model_name>.md` — locked face block, body specs, approved scenarios, voice

The web UI feeds the relevant files to the AI at generation time. To change how prompts are generated, edit those files.

## Accounts
- All accounts share one IG access token in `.env` as `IG_ACCESS_TOKEN`
- Token expires every ~60 days — regenerate via Meta Graph API Explorer
- `accounts.json` stores `name` and `ig_user_id` only

## Things to Never Do
- Do not commit `.env` or `accounts.json`
- Do not put the access token in `accounts.json`
- Do not rename photos without updating the load file
