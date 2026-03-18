# AuraScript

High-accuracy multi-language (Manglish / code-switching) transcription SaaS
powered by **Google Gemini 2.0 Flash** via Vertex AI.

---

## Architecture

```
Client ──HTTPS──► Nginx (TLS, rate-limit)
                    │
                    ▼
              FastAPI (port 8080)
              ├── POST /transcribe         → accept job (202)
              ├── GET  /transcribe/status  → poll job status
              ├── GET  /transcribe/result  → fetch completed transcript
              ├── DELETE /transcribe/:id   → cancel job
              ├── WS  /ws/transcribe/:id  → real-time events
              └── GET  /health[/ready]     → liveness / readiness

              Background pipeline (asyncio)
              ┌─ OrchestratorAgent ─────────────────────────────┐
              │  1. Analyze    ffprobe → AudioAnalysis           │
              │  2. Plan       chunk strategy                    │
              │  3. Chunk      ffmpeg → N × MP3 segments         │
              │  4. Transcribe TranscriptionAgent × N (parallel) │
              │  5. Quality    QualityAgent per chunk             │
              │  6. Retry      re-transcribe low-confidence      │
              │  7. Timestamps fix_chunk_timestamps per chunk    │
              │  8. Stitch     StitcherAgent (speaker unify)     │
              │  9. Complete   emit JobCompleteEvent             │
              └─────────────────────────────────────────────────┘

EventBus (asyncio.Queue per job) ──► ConnectionManager ──► WebSocket clients
                                 └──► WebhookService ──────► caller webhook URL
```

---

## Quick Start (local development)

### Prerequisites
- Docker + Docker Compose
- A GCP project with Vertex AI API enabled
- A GCP service account JSON with `roles/aiplatform.user`

### 1. Clone and configure
```bash
git clone https://github.com/anoop-au/aurascript-dev.git
cd aurascript-dev
cp aurascript/.env.example aurascript/.env
# Edit aurascript/.env — fill in all REQUIRED values
```

### 2. Place service account key
```bash
# Path must match GOOGLE_APPLICATION_CREDENTIALS in your .env
cp ~/Downloads/my-service-account.json ./service-account.json
```

### 3. Start
```bash
docker-compose up --build
```

API is available at `http://localhost:8080`.
Interactive docs (dev only): `http://localhost:8080/docs`

---

## Running Tests
```bash
pip install -r aurascript/requirements.txt -r aurascript/requirements-dev.txt
pytest aurascript/tests/ --cov=aurascript --cov-report=term-missing -v
```
Coverage gate: **80%** minimum.

---

## Deployment (Linode Ubuntu 22.04)

### First-time server setup
```bash
# As root on a fresh Linode
curl -sSL https://raw.githubusercontent.com/anoop-au/aurascript-dev/main/aurascript/scripts/setup_linode.sh | bash
```

This installs Docker, Nginx, Certbot, UFW; clones the repo; and starts the service.

### Post-setup manual steps
1. Edit `/opt/aurascript/aurascript/.env` — fill in all `REQUIRED` values
2. Place GCP service account JSON at `/opt/aurascript/secrets/service-account.json`
3. Point DNS: `www.aurascript.au` and `aurascript.store` → Linode IP
4. Issue SSL certificates:
   ```bash
   certbot --nginx \
     -d www.aurascript.au -d aurascript.au \
     -d www.aurascript.store -d aurascript.store
   ```
5. Restart: `cd /opt/aurascript && docker-compose -f docker-compose.yml -f docker-compose.prod.yml restart`

### GitHub Actions CI/CD
Add these secrets in GitHub → Settings → Secrets → Actions:

| Secret | Description |
|--------|-------------|
| `LINODE_HOST` | Linode VPS public IP |
| `LINODE_USER` | SSH user (e.g. `root`) |
| `LINODE_SSH_KEY` | Private key matching the VPS authorized_keys |

Every push to `main`:
1. **test** — runs pytest with 80% coverage gate
2. **build** — builds Docker image, pushes to `ghcr.io` tagged with git SHA
3. **deploy** — SSH into Linode, runs `deploy.sh`, runs `healthcheck.sh`

---

## API Reference

All endpoints except `/health` require:
```
X-Api-Key: <your-api-key>
```

### POST `/transcribe`
Submit an audio file for transcription.

**Form fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | File | Yes | Audio file (MP3, WAV, M4A, OGG, FLAC, AAC, WEBM) — max 700 MB |
| `language_hint` | string | No | Language hint (e.g. `"ms"`, `"en"`) |
| `num_speakers` | integer | No | Expected number of speakers (1–10) |
| `webhook_url` | string | No | HTTPS URL to receive completion webhook |

**Response 202:**
```json
{
  "job_id": "uuid",
  "status": "pending",
  "websocket_url": "wss://www.aurascript.au/ws/transcribe/{job_id}",
  "poll_url": "https://www.aurascript.au/transcribe/status/{job_id}",
  "result_url": "https://www.aurascript.au/transcribe/result/{job_id}",
  "message": "Job accepted. Connect to websocket_url for real-time updates."
}
```

### GET `/transcribe/status/{job_id}`
Poll job status. Returns `JobStatusResponse` with `status`, `progress_pct`, `error_code`.

### GET `/transcribe/result/{job_id}`
Fetch completed transcript. Returns `JobResultResponse` with `transcript`, `speaker_map`, `metadata`.
Returns 202 if still processing.

### DELETE `/transcribe/{job_id}`
Cancel a running job. Returns 204.

### WebSocket `/ws/transcribe/{job_id}?token=<api-key>`
Real-time event stream. Reconnect-safe: pass `last_sequence=N` query param to replay missed events.

**Event types:**
- `job.accepted` → `job.audio_analyzed` → `job.plan_created`
- `job.chunking_started` → `job.chunking_complete`
- `job.chunk_processing_started` → `job.chunk_transcribed` → `job.quality_checked`
- `job.chunk_retry` (if quality low)
- `job.stitching_started` → `job.stitching_complete`
- `job.complete` | `job.failed`
- `job.progress_heartbeat` (every 5s during transcription)

All events include: `event_type`, `job_id`, `timestamp`, `sequence`, `schema_version: "1.1"`.

### GET `/health`
Public liveness check. Returns `{"status": "ok", "version": "..."}`.

### GET `/health/ready`
Readiness check (verifies disk + Vertex AI config). Returns 503 if not ready.

### GET `/metrics`
Auth required. Returns job statistics.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VALID_API_KEYS` | Yes | Comma-separated API keys |
| `WEBHOOK_SECRET` | Yes | HMAC secret for webhook signing |
| `GOOGLE_CLOUD_PROJECT` | Yes | GCP project ID |
| `GOOGLE_CLOUD_LOCATION` | Yes | Vertex AI region (e.g. `us-central1`) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | Path to service account JSON |
| `GEMINI_MODEL` | No | Default: `gemini-2.0-flash-001` |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins |
| `MAX_CONCURRENT_JOBS` | No | Default: `5` |
| `MAX_AUDIO_DURATION_SECONDS` | No | Default: `7200` (2 hours) |
| `MAX_FILE_SIZE_BYTES` | No | Default: `734003200` (700 MB) |
| `CHUNK_DURATION_SECONDS` | No | Default: `300` (5 min) |
| `LOW_CONFIDENCE_THRESHOLD` | No | Default: `0.75` |
| `LOG_FORMAT` | No | `console` or `json` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

See [`.env.example`](.env.example) for the full list with documentation.

---

## Webhook Payload

On job completion, AuraScript POSTs to your `webhook_url`:

```json
{
  "event_type": "job.complete",
  "job_id": "uuid",
  "timestamp": "2024-01-01T00:00:00Z",
  "sequence": 42,
  "schema_version": "1.1",
  "transcript": "...",
  "speaker_map": {"Speaker 1": "Speaker 1"},
  "metadata": {"duration_seconds": 123.4, "chunk_count": 3}
}
```

Verify authenticity:
```python
import hmac, hashlib
expected = "sha256=" + hmac.new(
    WEBHOOK_SECRET.encode(), request.body, hashlib.sha256
).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-AuraScript-Signature"])
```

---

## Frontend Integration

This backend is designed to integrate with a **Lovable** frontend.
The WebSocket event stream and REST polling endpoints provide everything needed for:
- Real-time transcription progress UI
- Per-chunk confidence indicators
- Speaker-labeled transcript display
- File upload with progress tracking

See [FRONTEND_INTEGRATION.md](FRONTEND_INTEGRATION.md) for the complete integration spec (generated after frontend details are confirmed).

---

## Transcription Quality

AuraScript targets **97%+ accuracy** on Manglish (Malaysian English code-switching) audio:

- **Verbatim accuracy** — filler words, false starts, repetitions preserved exactly
- **Zero translation** — Malay words kept as spoken, never translated to English
- **Phonetic preservation** — Manglish pronunciation kept (`lah`, `mah`, `kan`, `lor`)
- **Uncertainty handling** — inaudible segments marked `[inaudible]`
- **Speaker diarization** — consistent `[Speaker X]:` labels across chunks
- **Timestamps** — `[MM:SS]` (or `[HH:MM:SS]` for >1 hour audio)

Each chunk is independently quality-scored (heuristic + AI validation gate) and automatically retried if confidence falls below threshold.
