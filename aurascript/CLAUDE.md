# AuraScript — Claude Code Context

## What This Is
AI-powered Manglish audio transcription PWA. FastAPI backend + Gemini 2.0 Flash.
Owner: Anoop Mukundan (anoop.mukundan7@gmail.com)

## Infrastructure
- **Linode IP**: 172.105.187.21
- **Backend**: https://api.aurascript.au → FastAPI/Uvicorn in Docker on 127.0.0.1:8080
- **Frontend**: https://www.aurascript.au → reverse proxy to echo-scribe-02.lovable.app
- **Secondary**: https://www.aurascript.store → redirects to www.aurascript.au
- **Repo**: github.com/anoop-au/aurascript-dev (private)

## Key Paths
- App code: /opt/aurascript/aurascript/
- Env file: /opt/aurascript/aurascript/.env
- Nginx config: /etc/nginx/sites-available/aurascript
- Docker compose: /opt/aurascript/docker-compose.prod.yml

## How to Restart
```bash
cd /opt/aurascript
docker compose -f docker-compose.prod.yml restart
docker logs aurascript-dev --tail 50
```

## Architecture
Upload → AudioAnalyzer → Planner → Chunker → TranscriptionAgent (parallel)
→ QualityAgent → Stitcher → JobComplete

## WebSocket Events (15 types)
ALL event_type values are lowercase dot-notation. NEVER uppercase.
job.accepted, job.audio_analyzed, job.plan_created, job.chunking_started,
job.chunking_complete, job.chunk_processing_started, job.chunk_transcribed,
job.quality_checked, job.chunk_retry, job.stitching_started,
job.stitching_complete, job.complete, job.failed, job.agent_decision,
job.progress_heartbeat

## Hard-Won Bug History (do not repeat)
1. Upload field is `file` not `audio_file`
2. Class-based FastAPI deps must use Header(alias=...) not Request injection
3. Progress field is `progress_pct` not `progress_percent`
4. MIME aliases needed: audio/mp3, audio/x-wav, audio/m4a, audio/x-flac, video/webm
5. Event types MUST be lowercase dot-notation — frontend silently drops UPPER_CASE
6. JobCompleteEvent must include transcript, speaker_map, metadata
7. aurascript.service systemd unit is DISABLED — app runs via Docker only
8. FastAPI 0.115.x + Pydantic v2: `Request` injection FAILS in class `__call__` methods entirely (treated as required query param → 422). Use `as_dependency()` closure pattern: class holds logic, method returns `async def _dep(request: Request)` closure. `Header(alias=...)` also fails in `__call__`.

## API
- Auth header: X-API-Key
- Base: https://api.aurascript.au
- Upload: POST /transcribe (multipart, field: `file`)
- Status: GET /jobs/{job_id}
- WebSocket: WS /ws/{job_id}
- Downloads: /jobs/{job_id}/download/{format} (txt/json/docx/pdf)

## Frontend
Lovable (React/Vite/Tailwind). VITE_API_BASE_URL must be https://api.aurascript.au
To redeploy frontend: push to Lovable or update env vars in Lovable project settings.

## Do Not Touch
- DNS settings (VentraIP)
- SSL certs (certbot, auto-renew)
- client_max_body_size 700M in nginx (intentional)
