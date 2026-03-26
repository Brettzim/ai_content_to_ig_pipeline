# AI Content to Instagram Pipeline

Generates AI-edited photos and videos from source images using the xAI Grok API, then posts them to Instagram via the Meta Graph API. Jobs are defined as JSON files dropped into the `loads/` folder.

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
```

**3. Configure secrets**

Create a `.env` file in the project root:
```
XAI_API_KEY=your_xai_api_key
IG_ACCESS_TOKEN=your_meta_access_token
```

**4. Configure accounts**

Create an `accounts.json` file:
```json
[
  { "name": "account_name", "ig_user_id": "123456789" }
]
```

**5. Add source photos**

Drop source images into the `photos/` folder.

## Running

```bash
venv\Scripts\python run.py                                        # run all loads, upload to IG
venv\Scripts\python run.py --no-upload                            # generate videos only
venv\Scripts\python run.py --loads-file loads/example.json       # single load file
```

## Load File Format

Create a `.json` file in the `loads/` folder:

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
| `photo` | Yes | Filename in `photos/` |
| `account` | Yes | Must match `name` in `accounts.json` |
| `post_type` | No | `"reel"` (default) or `"photo"` |
| `scene_prompt` | Yes | Describes the edited image |
| `video_prompt` | For reels | Describes the video motion and dialogue |
| `caption` | Yes | Instagram caption |

## Project Structure

```
loads/          # drop job JSON files here
photos/         # source images (not committed)
edited_photos/  # auto-generated intermediate images
videos/         # final generated videos
accounts.json   # IG account names and user IDs (not committed)
.env            # API keys and tokens (not committed)
```

## Notes

- The Instagram access token expires every ~60 days. Regenerate via Meta Graph API Explorer when posts start failing.
- `edited_photos/` and `videos/` are auto-created on first run.
