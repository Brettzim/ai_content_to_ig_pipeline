# Grok Pipeline — Claude Instructions

## What This Project Does
Generates AI videos from photos using the xAI Grok API, then posts them as Instagram Reels via the Meta Graph API. Jobs are defined in JSON files dropped into the `loads/` folder.

## Pipeline
1. **Image edit** — xAI edits the base photo to place the model in a new outfit/setting (`scene_prompt`)
2. **Video generation** — xAI animates the edited image with motion and dialogue (`video_prompt`)
3. **Instagram upload** — posts the video as a Reel with the caption

## How to Run
```bash
venv\Scripts\python run.py              # run all loads, upload to IG
venv\Scripts\python run.py --no-upload  # generate videos only
venv\Scripts\python run.py --loads-file loads/valentina_vixen.json  # single file
```

## Project Structure
- `loads/` — drop job JSON files here, one per model or campaign
- `photos/` — base source images, referenced by filename in load files
- `edited_photos/` — intermediate edited images (auto-generated, one per job)
- `videos/` — final generated videos
- `accounts.json` — Instagram accounts (name + ig_user_id only, no tokens)
- `.env` — secrets: XAI_API_KEY, IG_ACCESS_TOKEN

## Load File Format
```json
[
  {
    "photo": "filename.png",
    "account": "account_name",
    "post_type": "reel",
    "scene_prompt": "Place this woman in [outfit] at [setting]. Keep her face, hair, and body exactly the same.",
    "video_prompt": "Describe the motion, expression, and dialogue. Camera stays completely still.",
    "caption": "..."
  }
]
```
- `post_type` — `"reel"` (default) or `"photo"`. Controls whether a video is generated or the edited image is posted directly.
- `scene_prompt` — sent to xAI image editor to place the model in a new outfit/setting
- `video_prompt` — only required for `"reel"`. Not needed for `"photo"`.
- `account` must exactly match the `name` field in `accounts.json`

---

## Models

### Valentina Vixen
- **Account:** `valentina_vixen`
- **Photo:** `valentinavixen2.png`
- **Persona:** Sexy Latina domme with a hot mommy attitude. She shows off her lavish lifestyle. She is sexy and she knows it. Has total confidence. Seductive and dominant.
- **Aesthetic:** Lingerie, bedroom, bar, gym. classy dominatrix.
- **Scene prompt style:** Hotel bed, expensive resort, fancy restaurant, gym mirror. Dark tight outfits, lace, bodysuit.
- **Video prompt style:** Lock eyes with the camera, shows off her body, dominant woman energy. Bratty, in control.
- **Voice:** Commanding — she savors every word because she knows you're waiting on her. Bratty, declarative, slightly dismissive. e.g. `she says, commanding: 'A woman like me always gets what she wants.'`
- **Caption style:** Short, dismissive, one-liner energy. e.g. *"you already know you don't deserve me 🖤"*

### Mandy Woods
- **Account:** `mandy_woods`
- **Photo:** `mandywoods2.png`
- **Persona:** Tennis player who is built for the sport and impossible to ignore. Every movement on court — bending to pick up a ball, bouncing on her toes between points, pulling down her skirt after a dive — is unintentionally pornographic. She's focused on tennis. The camera is not.
- **Aesthetic:** Tennis is her thing but she posts from everywhere — court, track, gym, home. Minimal athletic wear in every setting: micro skirts and tight tops on court, sports bra and biker shorts on a run, fitted gym sets at the gym, something small and casual at home. Tan, toned, always slightly in motion.
- **Scene prompt style:** Rotate through settings — tennis court (baseline, net, courtside bench), outdoor run (track, park path, road), gym (mirror, cable machine, stretching mat), home (couch, kitchen counter, bed). Outfits always fitted and minimal for the setting. The body is always the story regardless of where she is.
- **Video prompt style:** Always doing something physical — serving, stretching, adjusting gear, cooling down, lifting. She notices the camera like it caught her mid-task. Every movement is the content.
- **Voice:** Warm and competitive — she's focused, confident, and doesn't need your approval. But she'll take your bet. e.g. `she says, warm and dry: 'you really think you could return that serve?'`
- **Caption style:** Tennis-brained. Competitive digs, match talk, court humor. e.g. *"love means nothing in tennis 🎾"* or *"first to 6 wins. you're already down 🤍"*

### Rachel Key
- **Account:** `rachel_key`
- **Photo:** `rachelkey1.jpg`
- **Persona:** Seductive e-girl who weaponizes cuteness. She knows exactly what thigh-highs and a crop top do to a guy who spends his nights gaming — and she dresses accordingly, every single time. Plays innocent while exposing her sexiest parts. She drains balls and wallets.
- **Aesthetic:** Gaming setup, sexy cosplay, neon/RGB lighting, anime-adjacent outfits. Outfits are always one size too small or one layer too few. Mix of cute and deeply distracting.
- **Scene prompt style:** Gaming chair with RGB setup, bedroom with neon lights, cosplay shoots. Crop tops, thigh-highs, short skirts, off-shoulder tops, cat ears, costumes that barely qualify as costumes.
- **Video prompt style:** Looking up from a screen with heavy-lidded eyes, adjusting a costume piece slowly, tilting her head and holding the stare a beat too long. Bubbly on the surface, completely intentional underneath.
- **Voice:** Bright and bubbly — sweet delivery on lines that aren't sweet at all. The innocence is the joke and she's in on it. e.g. `she says, bright and bubbly: 'don't stare. actually — you can stare.'`
- **Caption style:** Gamer references with a flirtatious sting. Plays dumb about how she looks. e.g. *"just a girl and her setup 💕 don't stare"* or *"it's just a costume 🎮🙈"*

### Zarah Gheller
- **Account:** `zarah_gheller`
- **Photo:** `zarahgheller.jpeg`
- **Persona:** Yogi-acrobat influencer. Extraordinarily flexible — she does things with her body that make people stop scrolling. The wellness branding is a cover; the real content is watching someone who moves like a dancer and bends like a contortionist look incredible doing it. Every pose pushes further than the last.
- **Aesthetic:** Yoga mats, beach at golden hour, rooftop at sunrise, airy studio. Outfits always minimal — barely-there two-piece sets, string bikini tops, high-waist bikini bottoms or biker shorts. The less fabric the better. Bare feet, perfect nails, tan skin.
- **Scene prompt style:** Extreme flexibility poses — full splits, standing splits, deep backbends, scorpion pose, chest-to-floor straddle, oversplit. Poses that require genuine flexibility and also happen to be visually stunning from every angle. Skin-baring outfits. Warm natural light. Always frame the pose from an angle that shows the full range of motion.
- **Video prompt style:** No dialogue — content is designed for viral music overlay. Pure movement only. Flow from one extreme flexibility pose into another, each one pushing deeper than the last. Beat structure: opening hold → first transition through a striking position → second deeper transition → final hold at the most extreme and visually stunning point. Every movement is slow and deliberate — the flexibility should look effortless, not strained. Never looks at the camera — she's in her practice.
- **Voice:** None — no dialogue in video prompts for Zarah.
- **Caption style:** Wellness quotes with an obvious double meaning. Airy, short, ends with a yoga hashtag. e.g. *"flexibility is a practice 🤍🧘‍♀️"* or *"open hips, open mind ✨ #yoga"*

---

## Prompt Writing Rules

Every word is an instruction. The model renders everything you write — there are no throwaway words. Build prompts the way an artist builds a drawing: most important information first, details layered in after.

---

### scene_prompt

**Structure (in order):**
1. **Camera angle first — always.** This is the lens everything is seen through. If it's wrong, nothing else saves the shot.
   - `Low angle view` — power, dominance, emphasizes the body
   - `Eye-level close-up` — intimate, direct, pulls the viewer in
   - `Candid POV` — natural, unposed, caught mid-moment
   - `Wide establishing shot` — shows full environment and figure
2. **Subject + key descriptors** — who is this, what do they look like
3. **Pose / expression** — what are they doing right now. Be specific about body position — weight, stance, what limbs are doing
4. **Wardrobe** — outfit, shoes, accessories, hair styling. For seductive content: describe fit (tight, fitted, barely-there), fabric (lace, satin, spandex), and coverage (cropped, micro, cut-out)
5. **Location** — be hyper-specific. "inside a moody bar with neon signs and dark wood" beats "at a bar"
6. **Style/mood/lighting** — cinematic grading, depth of field, warm/cool tones — always last. Golden hour and warm amber light are flattering; use them for skin
7. **Always include analog film descriptors** — the scene_prompt must always reference the Contax T2 camera and Kodak Ektar 100 film. Vary the following across prompts to keep content feeling distinct:
   - **Aperture:** rotate between `f/2.8` (very shallow, subject isolated), `f/4` (soft background, slight context), `f/5.6` (more environment visible)
   - **Film descriptors:** rotate between `fine grain analog realism`, `subtle film grain`, `rich analog texture`, `soft halation`
   - **Example:** `shot on a Contax T2, Kodak Ektar 100, 38mm f/2.8, shallow depth of field, fine grain analog realism`
   - Never use the exact same descriptor string twice in a row
8. **Always end with:** `Keep her face, hair, and body exactly the same.`

**Template:**
```
[Camera angle] of a [descriptors] woman with [features]. She [pose/expression] wearing [outfit] and [shoes]. Inside/at [specific location]. [Lighting and mood descriptors]. Keep her face, hair, and body exactly the same.
```

**Do not say "full body."** It makes the model interpret "full-bodied" as a body type. Instead, describe shoes, leg stance, and the ground — the model will be forced to render the full figure.

**Word precision:** Synonyms are not interchangeable. Test descriptors you're unsure about. Words carry unintended associations from training data.

---

### Scene/Video Consistency Rule

**The video prompt must be physically consistent with the scene prompt.** Before writing the video prompt, check:
- Which direction is the subject facing?
- What is in front of her vs. behind her?
- What is she holding or touching?
- What can she realistically interact with given her position?

**Example of the mistake to avoid:** Scene puts a gaming monitor behind the subject (she faces camera), but video has her leaning toward the monitor — she can't interact with something that's behind her. If the setup is behind her, the video action must use what's in front of her (a controller, her hands, the camera itself).

When in doubt: re-read the scene_prompt and mentally place yourself in the shot before writing a single word of the video_prompt.

---

### video_prompt

The model uses the formula: **Subject motion + Background motion + Camera motion.** Write all three.

**Structure (in order):**
1. **Camera angle first** — same rule applies. Set the perspective before anything else.
2. **3-4 distinct beats to fill 10 seconds** — each beat ~2-3 seconds. Chain: opening movement → reaction → dialogue → closing expression. A vague prompt produces awkward filler.
3. **Subject motion** — describe exactly what she does, using adverbs for intensity. `slowly`, `deliberately`, `barely`, `powerfully` all change how the model renders the action. Be specific about which body part moves.
4. **Background motion** — always add subtle ambient movement. This makes the scene feel alive rather than frozen. Match it to the environment:
   - Outdoors: `a light breeze moves through her hair`, `leaves shift softly behind her`, `the water surface ripples gently`
   - Indoor/bar: `candle flame flickers`, `ambient light shifts slightly`
   - Urban/night: `city lights pulse softly in the background`
5. **Include dialogue** — have the subject say something that matches the caption vibe. Use the character's voice profile: embed tone as 1-2 adjectives directly in the verb phrase. `she says, commanding:` / `she says, warm and dry:` / `she says, bright and bubbly:` / `she says, calm and knowing:`. No metaphors — tone words only.
6. **Keep subject motion subtle** — breathing, head turns, weight shifts, hair movement. No jumping or dramatic movement. The body is the content — slow and deliberate reads as confident and seductive.
7. **Camera motion** — default is `Camera stays completely still.` This is almost always correct for our style. Only use camera movement (slow zoom, slight pan) if the scene specifically calls for it — keep it minimal.

**Template:**
```
[Camera angle]. [Beat 1: opening subject movement + background motion begins]. [Beat 2: reaction or shift]. [Beat 3: dialogue — she says "[line]"]. [Beat 4: closing expression]. Camera stays completely still.
```

**Example of a well-paced 10s prompt:**
*"Eye-level close-up. She exhales slowly and rolls her neck to one side, hair shifting with the movement, a faint breeze catching the ends. Her eyes drift to the camera — not quite looking, just aware of it. She tucks her bottom lip in for a half second, then lets a slow smile spread. She says, commanding: 'I know' — almost to herself, then looks away. Camera stays completely still."*

## Caption Rules
- Emojis are supported — JSON files must be saved as UTF-8
- Keep captions short and in-character
- Match the dialogue/action in the video_prompt

## Accounts
- All accounts share one IG access token stored in `.env` as `IG_ACCESS_TOKEN`
- Token expires every ~60 days — regenerate via Meta Graph API Explorer when posts start failing
- `accounts.json` only stores `name` and `ig_user_id`

## Things to Never Do
- Do not put the access token back into `accounts.json`
- Do not commit `.env` or `accounts.json` to git
- Do not rename photos without updating the corresponding load file
- Do not change poll intervals without a good reason (xAI: 10s, IG container: 20s)
