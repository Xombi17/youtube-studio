# GitHub Actions — Clip Review & Auto-Publish Setup

This guide connects the **GitHub Actions scheduler** to your existing
`publish_agent.py` pipeline so clips are reviewed and published/deleted
automatically every day without your machine needing to be on.

---

## How it works

```
Live Clipper (--auto-upload)
        │  score ≥ 80 / 85
        ▼
  YouTube (PRIVATE draft)
  + config/youtube_upload_history.json (staged)
        │
        │ GitHub Actions (cron: 19:00 IST + 10:00 IST)
        ▼
  publish_agent.py
   ├── human_clip_reviewer.py  →  POST / MAYBE / SKIP
   ├── POST + peak window open  →  set_video_privacy(public)
   └── MAYBE / SKIP             →  delete_video() + rm local package
```

GitHub Actions runs `scripts/publish_agent.py` **twice per day**:

| Cron | IST time | Purpose |
|------|----------|---------|
| `30 13 * * *` | 19:00 | Peak window — publish approved clips |
| `30 4  * * *` | 10:00 | Morning pass — review + clean up rejects |

You can also trigger it manually from the **Actions** tab with optional
`--dry-run` or `--publish-now` overrides.

---

## One-time setup

### 1. Required GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**
and add all of the following:

| Secret name | How to get it |
|-------------|---------------|
| `YOUTUBE_TOKEN_CLIPPER` | Contents of `config/youtube_token_clipper.json` |
| `YOUTUBE_CLIENT_SECRET_CLIPPER` | Contents of `config/youtube_client_secret_clipper.json` |
| `YOUTUBE_UPLOAD_HISTORY` | Contents of `config/youtube_upload_history.json` |
| `GROQ_API_KEY` | Your Groq free-tier key |
| `APINEX_API_KEY` | Your APInex key (optional — improves reviewer quality) |
| `ADMIN_TOKEN` | A GitHub PAT with `repo` + `secrets` scope (needed to persist the upload history back after each run) |

> **Important:** `YOUTUBE_UPLOAD_HISTORY` is the live state file.  
> The workflow reads it at run-start and writes the updated version back
> using `ADMIN_TOKEN` at the end. Without `ADMIN_TOKEN`, each run starts
> fresh — clips already published/deleted will be re-processed.

### 2. Enable auto-upload in the clipper

Add `--auto-upload` (and optionally `--auto-upload-min-score 80`) when
you launch the live clipper:

```bash
# Stage clips scoring ≥ 80 as private YouTube drafts
python orchestration/live_clipper_agent.py \
  --auto-upload \
  --auto-upload-min-score 80 \
  --upload-privacy private \
  ...your-other-flags...
```

The score threshold choices:

| Score | Recommended use |
|-------|----------------|
| `85` | Tighter filter — only near-certain bangers staged (default) |
| `80` | Wider net — more clips staged, more for the reviewer to cut |

### 3. Push the workflow

```bash
git add .github/workflows/clip-reviewer.yml README-GITHUB-ACTIONS.md
git commit -m "feat: add GitHub Actions clip review & publish workflow"
git push
```

GitHub will start running the cron automatically.

---

## Manual trigger

Go to **Actions → 🎬 Clip Review & Publish Agent → Run workflow**.

Options:
- **Dry run** — reports what would happen without touching YouTube
- **Publish now** — ignores the 19:00–22:00 peak window

---

## Adjusting the publish window

Edit `config/clipper-publish.json`:

```json
{
  "peak_window": {
    "start": "19:00",
    "end": "22:00",
    "timezone": "Asia/Kolkata"
  },
  "max_publish_per_run": 4,
  "max_delete_per_run": 25
}
```

Commit the change and the next scheduled run picks it up.

---

## Reading the results

After each run, open **Actions → the run → job summary**.  
You'll see a table of published clips (with score + gut reaction),
rejected clips, and any errors.

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `YouTubeScopeError: missing force-ssl scope` | Re-auth locally: `python scripts/youtube_uploader.py --auth --profile clipper`, then update `YOUTUBE_TOKEN_CLIPPER` secret |
| `0 staged clips found` | Make sure `YOUTUBE_UPLOAD_HISTORY` is up-to-date and clips were staged with `--auto-upload` |
| `ADMIN_TOKEN not set` | Add a PAT with `secrets` write scope; without it, state is lost between runs |
| `reviewer unavailable` | Check `GROQ_API_KEY` / `APINEX_API_KEY` secrets are set |
