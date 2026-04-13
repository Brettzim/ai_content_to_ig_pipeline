# Grok Pipeline — Claude Instructions

## What This Project Does
Generates AI images and videos from photos using the xAI Grok API, then posts them to Instagram via the Meta Graph API. Jobs are defined in JSON files in `loads/` or triggered via the web UI.

## How to Run

```bash
# Web UI (preferred)
venv\Scripts\python web_app.py
# Open http://localhost:5000

# CLI — run all loads
venv\Scripts\python run.py

# CLI — single file, no upload
venv\Scripts\python run.py --loads-file loads/valentina_vixen.json --no-upload
```

## Project Structure

```
personas/              — per-model folders with profile .md, reference photos, history
prompt_engineering/    — universal prompt rules (scene, video, reels, engagement, creative direction)
loads/                 — CLI job JSON files (one per model)
photos/                — source images
edited_photos/         — auto-generated intermediate images
videos/                — final generated videos
accounts.json          — Instagram accounts (name + ig_user_id only, no tokens)
.env                   — secrets: XAI_API_KEY, IG_ACCESS_TOKEN
web_app.py             — Flask web UI
run.py                 — CLI pipeline runner
```

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
