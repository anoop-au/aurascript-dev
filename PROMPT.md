





Start with Phase 1 ONLY. Stop and wait for me to type CONTINUE before starting Phase 2.





╔══════════════════════════════════════════════════════════════════════════╗

║           AURASCRIPT TRANSCRIPTION SAAS — MASTER BUILD PROMPT           ║

║                     Input this entire prompt to your                     ║

║                    VS Code AI Dev Agent (Claude Code)                 ║

╚══════════════════════════════════════════════════════════════════════════╝



You are a senior Python backend engineer building AuraScript — a 

production-ready, monetizable, high-accuracy multi-language code-switching enabled transcription SaaS.



PRODUCT IDENTITY:

&#x20; App Name:     AuraScript

&#x20; Domain 1:     https://www.aurascript.au     (primary)

&#x20; Domain 2:     https://www.aurascript.store  (secondary)

&#x20; Tagline:      "Your voice, every language, perfectly captured."

&#x20; Target:       97%+ accuracy on Manglish or any such hybrid code-switching audio

&#x20; Infra:        Linode (Linux VPS) + GitHub repository

&#x20; Frontend:     Lovable.dev (published, integration deferred to Phase 2)

&#x20; AI Backend:   Google Gemini 2.0 Flash (via Vertex AI)



══════════════════════════════════════════════════════════════════════════

AGENT BEHAVIOUR RULES (Read before generating any code)

══════════════════════════════════════════════════════════════════════════



Rule 1 — BUILD SEQUENTIALLY.

&#x20; Generate code in the exact phase order defined below.

&#x20; Do not skip ahead. Do not merge phases.



Rule 2 — STOP AND CONFIRM AFTER EACH PHASE.

&#x20; After completing each phase, print this exact message and WAIT:

&#x20; ┌─────────────────────────────────────────────────────────┐

&#x20; │ ✅ PHASE \[N] COMPLETE                                    │

&#x20; │ Files generated: \[list every file created]              │

&#x20; │ Next: \[describe Phase N+1 in one sentence]              │

&#x20; │ Type CONTINUE to proceed or STOP to pause.              │

&#x20; └─────────────────────────────────────────────────────────┘



Rule 3 — INTEGRATION GATE (CRITICAL — DO NOT SKIP).

&#x20; After Phase 7 (Linode deployment verified), the agent MUST stop

&#x20; and print this EXACT message before writing any integration code:



&#x20; ┌─────────────────────────────────────────────────────────────────┐

&#x20; │ 🔗 INTEGRATION GATE — ACTION REQUIRED                           │

&#x20; │                                                                  │

&#x20; │ The AuraScript backend is live. Before I write any frontend      │

&#x20; │ integration code, I need the following from your Lovable app:    │

&#x20; │                                                                  │

&#x20; │ Please provide:                                                  │

&#x20; │                                                                  │

&#x20; │ 1. LOVABLE APP URL                                               │

&#x20; │    What is the published URL of your Lovable frontend?           │

&#x20; │    (e.g., https://aurascript.lovable.app)                        │

&#x20; │                                                                  │

&#x20; │ 2. LOVABLE APP ORIGIN                                            │

&#x20; │    What exact origin should the backend CORS whitelist?          │

&#x20; │    (Provide all origins including preview URLs if any)           │

&#x20; │                                                                  │

&#x20; │ 3. AUTHENTICATION METHOD                                         │

&#x20; │    How will the Lovable frontend send the API key?               │

&#x20; │    Option A: X-API-Key request header (recommended)              │

&#x20; │    Option B: Bearer token in Authorization header                │

&#x20; │    Option C: Query parameter (least secure, WebSocket only)      │

&#x20; │                                                                  │

&#x20; │ 4. UPLOAD TRIGGER                                                │

&#x20; │    Does the Lovable app upload audio directly from the browser   │

&#x20; │    or via a backend relay?                                       │

&#x20; │    Option A: Direct browser → AuraScript API upload              │

&#x20; │    Option B: Lovable backend → AuraScript API relay              │

&#x20; │                                                                  │

&#x20; │ 5. REAL-TIME DISPLAY PREFERENCE                                  │

&#x20; │    How should the frontend receive transcription progress?       │

&#x20; │    Option A: WebSocket (recommended, real-time chunk-by-chunk)   │

&#x20; │    Option B: Webhook POST to a Lovable endpoint                  │

&#x20; │    Option C: HTTP polling every N seconds                        │

&#x20; │    Option D: All three (generate all integration paths)          │

&#x20; │                                                                  │

&#x20; │ 6. RESULT DELIVERY                                               │

&#x20; │    After transcription completes, how should results be served?  │

&#x20; │    Option A: Frontend fetches GET /transcribe/result/{job\_id}    │

&#x20; │    Option B: Backend pushes final result via WebSocket           │

&#x20; │    Option C: Webhook delivery to Lovable endpoint                │

&#x20; │                                                                  │

&#x20; │ 7. FILE SIZE EXPECTATION                                         │

&#x20; │    What is the typical audio file size your users will upload?   │

&#x20; │    (This affects timeout and UX copy in integration code)        │

&#x20; │                                                                  │

&#x20; │ 8. LOVABLE COMPONENT NAMES (optional but speeds integration)     │

&#x20; │    If you know the names of your Lovable components, provide:    │

&#x20; │    - Upload component name                                       │

&#x20; │    - Progress display component name                             │

&#x20; │    - Transcript display component name                           │

&#x20; │                                                                  │

&#x20; │ ⏳ Waiting for your answers before proceeding to Phase 8...      │

&#x20; └─────────────────────────────────────────────────────────────────┘



Rule 4 — NO PLACEHOLDERS.

&#x20; Every function must be fully implemented.

&#x20; No TODO comments. No `pass` in non-abstract methods.

&#x20; No `# implement this later` comments.



Rule 5 — TYPE SAFETY EVERYWHERE.

&#x20; Python 3.11+ type hints on every function signature.

&#x20; Pydantic v2 syntax throughout (model\_dump, model\_validate).

&#x20; Annotated constraints on all numeric and string fields.



Rule 6 — NEVER HARDCODE SECRETS.

&#x20; All secrets, keys, URLs loaded from environment variables only.

&#x20; If a value looks like a secret and it is hardcoded, it is a bug.



Rule 7 — TEST AS YOU BUILD.

&#x20; Generate the test file for each service immediately after that 

&#x20; service file. Do not batch tests at the end.



══════════════════════════════════════════════════════════════════════════

PROJECT STRUCTURE (generate exactly this, no additions, no omissions)

══════════════════════════════════════════════════════════════════════════



aurascript/

├── main.py                          # FastAPI app + lifespan

├── config.py                        # Pydantic Settings

├── dependencies.py                  # Shared FastAPI DI

│

├── routers/

│   ├── \_\_init\_\_.py

│   ├── transcription.py             # HTTP endpoints

│   ├── websocket.py                 # WebSocket endpoint

│   └── health.py                    # Health + metrics

│

├── agents/

│   ├── \_\_init\_\_.py

│   ├── base\_agent.py                # Abstract base

│   ├── orchestrator.py              # Master planner agent

│   ├── transcription\_agent.py       # Phase 1: Gemini Pro per-chunk

│   ├── quality\_agent.py             # Quality scorer + retry decider

│   └── stitcher\_agent.py            # Phase 2: Gemini Flash unifier

│

├── services/

│   ├── \_\_init\_\_.py

│   ├── audio\_processor.py           # FFmpeg/ffprobe async wrapper

│   ├── event\_bus.py                 # Internal async pub/sub

│   ├── pipeline.py                  # Top-level job orchestration

│   └── webhook\_service.py           # Outbound webhook delivery

│

├── core/

│   ├── \_\_init\_\_.py

│   ├── security.py                  # API key auth + rate limiting

│   ├── storage.py                   # Safe async file I/O

│   ├── job\_store.py                 # Job state machine

│   └── connection\_manager.py        # WebSocket session registry

│

├── models/

│   ├── \_\_init\_\_.py

│   ├── schemas.py                   # HTTP request/response models

│   ├── events.py                    # Typed WebSocket event models

│   └── agent\_state.py               # Agent I/O dataclasses

│

├── utils/

│   ├── \_\_init\_\_.py

│   ├── timestamp\_math.py            # Chunk offset calculations

│   └── cleanup.py                   # Guaranteed temp file deletion

│

├── tests/

│   ├── \_\_init\_\_.py

│   ├── conftest.py                  # Shared fixtures

│   ├── test\_timestamp\_math.py

│   ├── test\_audio\_processor.py

│   ├── test\_security.py

│   ├── test\_agents.py

│   ├── test\_websocket.py

│   └── test\_events.py

│

├── scripts/

│   ├── setup\_linode.sh              # One-command Linode VPS setup

│   ├── deploy.sh                    # Git pull + restart service

│   └── healthcheck.sh               # Post-deploy verification

│

├── .github/

│   └── workflows/

│       └── deploy.yml               # GitHub Actions CI/CD to Linode

│

├── nginx/

│   └── aurascript.conf              # Nginx reverse proxy config

│

├── .env.example                     # All env vars documented

├── .env.test                        # Safe test env vars (no secrets)

├── .gitignore

├── requirements.txt                 # Pinned versions

├── requirements-dev.txt             # Test + lint tools

├── Dockerfile

├── docker-compose.yml               # Local dev environment

├── docker-compose.prod.yml          # Production override

├── FRONTEND\_INTEGRATION.md          # Lovable integration guide

└── README.md                        # Setup + deployment guide



══════════════════════════════════════════════════════════════════════════

PHASE 1 — CONFIGURATION \& FOUNDATION

Files: config.py, .env.example, .env.test, .gitignore

══════════════════════════════════════════════════════════════════════════



Generate config.py using pydantic-settings BaseSettings.



Include ALL of these settings with types, defaults, and inline comments:



class Settings(BaseSettings):

&#x20;   # ── Identity ──────────────────────────────────────────────────────

&#x20;   APP\_NAME: str = "AuraScript"

&#x20;   APP\_VERSION: str = "1.0.0"

&#x20;   ENVIRONMENT: Literal\["development", "staging", "production"] = "development"



&#x20;   # ── Server ────────────────────────────────────────────────────────

&#x20;   HOST: str = "0.0.0.0"

&#x20;   PORT: int = 8080

&#x20;   # Primary domain. Used to construct absolute URLs in API responses.

&#x20;   PRIMARY\_DOMAIN: str = "https://www.aurascript.au"

&#x20;   # Secondary domain. Redirects handled at Nginx level.

&#x20;   SECONDARY\_DOMAIN: str = "https://www.aurascript.store"



&#x20;   # ── CORS ──────────────────────────────────────────────────────────

&#x20;   # Comma-separated list. Must include both aurascript domains

&#x20;   # AND the Lovable app origin once known.

&#x20;   ALLOWED\_ORIGINS: list\[str] = \[

&#x20;       "https://www.aurascript.au",

&#x20;       "https://www.aurascript.store",

&#x20;       "http://localhost:3000",         # Local Lovable dev

&#x20;       "http://localhost:5173",         # Vite dev server

&#x20;   ]



&#x20;   # ── Google Vertex AI ──────────────────────────────────────────────

&#x20;   GOOGLE\_CLOUD\_PROJECT: str

&#x20;   GOOGLE\_CLOUD\_LOCATION: str = "us-central1"

&#x20;   GOOGLE\_APPLICATION\_CREDENTIALS: str   # Path to service account JSON

&#x20;   VERTEX\_AI\_MODEL\_TRANSCRIBE: str = "gemini-2.0-flash"

&#x20;   VERTEX\_AI\_MODEL\_STITCH: str = "gemini-2.0-flash"

&#x20;   VERTEX\_AI\_MODEL\_QUALITY: str = "gemini-2.0-flash"



&#x20;   # ── Security ──────────────────────────────────────────────────────

&#x20;   # Comma-separated API keys. Rotate without restart.

&#x20;   VALID\_API\_KEYS: set\[str]

&#x20;   API\_KEY\_HEADER: str = "X-API-Key"

&#x20;   WEBHOOK\_SECRET: str   # HMAC-SHA256 signing key for webhook payloads

&#x20;   MAX\_REQUESTS\_PER\_MINUTE: int = 10

&#x20;   MAX\_REQUESTS\_PER\_DAY: int = 200   # Cost control per API key



&#x20;   # ── File Handling ─────────────────────────────────────────────────

&#x20;   MAX\_UPLOAD\_SIZE\_BYTES: int = 734\_003\_200   # 700MB

&#x20;   UPLOAD\_DIR: Path = Path("/tmp/aurascript/uploads")

&#x20;   CHUNKS\_DIR: Path = Path("/tmp/aurascript/chunks")

&#x20;   ALLOWED\_AUDIO\_MIME\_TYPES: list\[str] = \[

&#x20;       "audio/mpeg", "audio/wav", "audio/mp4", "audio/ogg",

&#x20;       "audio/webm", "audio/flac", "audio/x-m4a", "audio/aac",

&#x20;   ]



&#x20;   # ── Processing ────────────────────────────────────────────────────

&#x20;   CHUNK\_DURATION\_SECONDS: int = 180        # 3 minutes per chunk

&#x20;   MAX\_CONCURRENT\_GEMINI\_CALLS: int = 5     # Semaphore limit

&#x20;   MAX\_AUDIO\_DURATION\_SECONDS: int = 7200   # 2-hour hard limit

&#x20;   QUALITY\_SCORE\_THRESHOLD: float = 0.6     # Below = retry

&#x20;   LOW\_CONFIDENCE\_THRESHOLD: float = 0.4   # Below = flag

&#x20;   MAX\_QUALITY\_RETRIES: int = 1             # Retry once, flag if still bad



&#x20;   # ── Jobs ──────────────────────────────────────────────────────────

&#x20;   JOB\_TTL\_SECONDS: int = 3600        # 1 hour before auto-cleanup

&#x20;   MAX\_CONCURRENT\_JOBS: int = 10      # Linode resource protection



&#x20;   # ── WebSocket ─────────────────────────────────────────────────────

&#x20;   WS\_PING\_INTERVAL\_SECONDS: int = 25

&#x20;   WS\_PING\_TIMEOUT\_SECONDS: int = 10

&#x20;   WS\_MAX\_RECONNECT\_HISTORY: int = 100  # Events to cache per job



&#x20;   # ── Observability ─────────────────────────────────────────────────

&#x20;   LOG\_LEVEL: str = "INFO"

&#x20;   LOG\_FORMAT: Literal\["json", "console"] = "json"



&#x20;   model\_config = SettingsConfig(

&#x20;       env\_file=".env",

&#x20;       env\_file\_encoding="utf-8",

&#x20;       case\_sensitive=True

&#x20;   )



&#x20;   @field\_validator("ALLOWED\_ORIGINS", mode="before")

&#x20;   @classmethod

&#x20;   def parse\_origins(cls, v: str | list) -> list\[str]:

&#x20;       # Accept comma-separated string from env var

&#x20;       if isinstance(v, str):

&#x20;           return \[o.strip() for o in v.split(",")]

&#x20;       return v



&#x20;   @property

&#x20;   def is\_production(self) -> bool:

&#x20;       return self.ENVIRONMENT == "production"



&#x20;   @property

&#x20;   def websocket\_base\_url(self) -> str:

&#x20;       # Returns wss:// in production, ws:// in development

&#x20;       if self.is\_production:

&#x20;           return f"wss://www.aurascript.au"

&#x20;       return f"ws://localhost:{self.PORT}"



Generate .env.example with EVERY variable, each with a comment 

explaining what it does and how to generate secret values.

Mark every secret with # REQUIRED — generate with: openssl rand -hex 32



Generate .gitignore that ignores:

&#x20; .env, .env.\*, !.env.example, !.env.test

&#x20; \_\_pycache\_\_, \*.pyc, .pytest\_cache

&#x20; /tmp, \*.audio, \*.mp3 (never commit audio files)

&#x20; .venv, venv, node\_modules

&#x20; \*.log, logs/

&#x20; service-account.json, \*credentials\*.json



══════════════════════════════════════════════════════════════════════════

PHASE 2 — CORE SECURITY \& STORAGE

Files: core/security.py, core/storage.py, core/job\_store.py,

&#x20;      tests/test\_security.py

══════════════════════════════════════════════════════════════════════════



── core/security.py ────────────────────────────────────────────────────



Implement `APIKeyAuth` class as a FastAPI dependency:



&#x20; - Extract key from X-API-Key header (configurable via settings).

&#x20; - Validate using `secrets.compare\_digest` against VALID\_API\_KEYS set.

&#x20; - On failure: raise HTTP 401, body: {"error": "Unauthorized"}

&#x20;   NEVER indicate whether the key format was wrong or key was unknown.

&#x20; - On success: return the validated key string (used as rate limit ID).



Implement `RateLimiter` class:



&#x20; - TWO limits: per-minute (burst) AND per-day (cost control).

&#x20; - Use sliding window counter per API key in an asyncio-safe dict.

&#x20; - Use `asyncio.Lock` per key, created lazily.

&#x20; - Per-minute breach: HTTP 429 with header Retry-After: {seconds}

&#x20; - Per-day breach: HTTP 429 with body message indicating daily limit.

&#x20; - Provide `async def reset\_key(api\_key: str)` for admin use.

&#x20; - Provide `def get\_usage\_stats(api\_key: str) -> dict` for metrics.



Implement `verify\_webhook\_signature(payload: bytes, signature: str) -> bool`:

&#x20; - HMAC-SHA256 verification for inbound webhook calls.

&#x20; - Use `secrets.compare\_digest`.



── core/storage.py ─────────────────────────────────────────────────────



Implement `SafeFileStorage` class:



`async def save\_upload(file: UploadFile, job\_id: str) -> Path`:

&#x20; - Validate content\_type against ALLOWED\_AUDIO\_MIME\_TYPES whitelist.

&#x20; - Validate magic bytes (first 512 bytes) using python-magic.

&#x20;   Reject files whose magic bytes do not match an audio format.

&#x20; - Generate filename: f"{job\_id}\_{uuid4().hex\[:8]}.audio"

&#x20;   NEVER use the original filename from the client.

&#x20; - Ensure UPLOAD\_DIR exists (create if not).

&#x20; - Stream to disk using aiofiles in 1MB chunks.

&#x20; - Count bytes as you stream. If MAX\_UPLOAD\_SIZE\_BYTES exceeded:

&#x20;   \* Stop streaming immediately.

&#x20;   \* Delete the partial file.

&#x20;   \* Raise HTTP 413 with message "File exceeds 700MB limit."

&#x20; - Return the resolved absolute Path.



`async def cleanup\_job\_files(paths: list\[Path]) -> dict\[str, bool]`:

&#x20; - Attempt deletion of every path.

&#x20; - Per-file try/except: one failure must not block others.

&#x20; - Log each deletion at DEBUG level.

&#x20; - Log failures at WARNING level with the exception message.

&#x20; - Return dict mapping str(path) → True (deleted) / False (failed).



`async def scan\_orphaned\_files(max\_age\_hours: int = 2) -> list\[Path]`:

&#x20; - Scan UPLOAD\_DIR and CHUNKS\_DIR for files older than max\_age\_hours.

&#x20; - Return list of orphaned Paths for startup recovery.



── core/job\_store.py ───────────────────────────────────────────────────



Define `JobStatus` enum:

&#x20; PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED



Define `JobRecord` dataclass:

&#x20; job\_id: str

&#x20; status: JobStatus

&#x20; created\_at: datetime

&#x20; updated\_at: datetime

&#x20; completed\_at: Optional\[datetime]

&#x20; language\_hint: str

&#x20; num\_speakers: int

&#x20; webhook\_url: Optional\[str]

&#x20; file\_paths: list\[Path]           # All paths for cleanup

&#x20; chunk\_paths: list\[Path]          # Populated after chunking

&#x20; transcript: Optional\[str]

&#x20; speaker\_map: Optional\[dict\[str, str]]

&#x20; metadata: Optional\[dict]         # languages, confidence, word\_count etc

&#x20; error\_code: Optional\[str]

&#x20; error\_message: Optional\[str]

&#x20; progress\_percent: float = 0.0

&#x20; current\_stage: str = "PENDING"

&#x20; task\_handle: Optional\[asyncio.Task] = None   # For cancellation



Implement `JobStore` class:

&#x20; - Storage: `dict\[str, JobRecord]` with `asyncio.Lock` for writes.

&#x20; - `async def create\_job(...) -> JobRecord`

&#x20; - `async def update\_job(job\_id, \*\*kwargs) -> JobRecord`

&#x20; - `async def get\_job(job\_id) -> Optional\[JobRecord]`

&#x20; - `async def cancel\_job(job\_id) -> bool`:

&#x20;     Cancel task\_handle if it exists. Update status to CANCELLED.

&#x20; - `async def cleanup\_expired\_jobs() -> int`:

&#x20;     Delete jobs older than JOB\_TTL\_SECONDS. Return count deleted.

&#x20; - `def get\_stats() -> dict`:

&#x20;     Return counts by status + average processing time.

&#x20; - Hard limit: reject new jobs if PROCESSING count >= MAX\_CONCURRENT\_JOBS.

&#x20;   Raise HTTP 503 with Retry-After header.



── tests/test\_security.py ──────────────────────────────────────────────



Generate pytest tests covering:

&#x20; - Valid API key → 200 on a protected endpoint

&#x20; - Invalid API key → 401, body does not contain "key" or "token"

&#x20; - Rate limiter per-minute → 429 after MAX\_REQUESTS\_PER\_MINUTE+1 calls

&#x20; - Rate limiter per-day → 429 after MAX\_REQUESTS\_PER\_DAY+1 calls

&#x20; - 429 response includes Retry-After header

&#x20; - Webhook signature valid → True

&#x20; - Webhook signature tampered → False

&#x20; - Error responses never contain stack traces or internal paths



Use httpx AsyncClient + pytest-asyncio.



══════════════════════════════════════════════════════════════════════════

PHASE 3 — EVENT SYSTEM

Files: models/events.py, models/agent\_state.py, services/event\_bus.py,

&#x20;      core/connection\_manager.py, tests/test\_events.py

══════════════════════════════════════════════════════════════════════════



── models/events.py ────────────────────────────────────────────────────



THIS IS THE PUBLIC API CONTRACT WITH THE LOVABLE FRONTEND.

Treat it as a versioned public interface.

NEVER remove or rename fields. Only add Optional fields.



from \_\_future\_\_ import annotations

from datetime import datetime

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field



class BaseEvent(BaseModel):

&#x20;   """

&#x20;   Base for all WebSocket events.

&#x20;   Frontend uses event\_type as discriminator for switch/case routing.

&#x20;   sequence is monotonically increasing per job.

&#x20;   Frontend detects dropped messages by checking for gaps in sequence.

&#x20;   schema\_version enables future non-breaking evolution.

&#x20;   """

&#x20;   event\_type: str

&#x20;   job\_id: str

&#x20;   timestamp: datetime

&#x20;   sequence: int

&#x20;   schema\_version: Literal\["1.1"] = "1.1"



class JobAcceptedEvent(BaseEvent):

&#x20;   event\_type: Literal\["JOB\_ACCEPTED"]

&#x20;   file\_size\_bytes: int

&#x20;   file\_name\_safe: str

&#x20;   poll\_url: str

&#x20;   # websocket\_url NOT included: client is already connected



class AudioAnalyzedEvent(BaseEvent):

&#x20;   event\_type: Literal\["AUDIO\_ANALYZED"]

&#x20;   duration\_seconds: float

&#x20;   sample\_rate: int

&#x20;   channels: int

&#x20;   codec: str

&#x20;   bitrate\_kbps: Optional\[int]        # None for VBR audio

&#x20;   is\_stereo: bool

&#x20;   quality\_warnings: list\[str]        # Immediate warnings from ffprobe



class PlanCreatedEvent(BaseEvent):

&#x20;   event\_type: Literal\["PLAN\_CREATED"]

&#x20;   estimated\_chunks: int

&#x20;   strategy: Literal\["single\_chunk", "multi\_chunk", "large\_file\_warning"]

&#x20;   estimated\_processing\_minutes: float

&#x20;   chunk\_duration\_seconds: int



class ChunkingStartedEvent(BaseEvent):

&#x20;   event\_type: Literal\["CHUNKING\_STARTED"]

&#x20;   total\_expected\_chunks: int



class ChunkingCompleteEvent(BaseEvent):

&#x20;   event\_type: Literal\["CHUNKING\_COMPLETE"]

&#x20;   actual\_chunk\_count: int

&#x20;   total\_audio\_seconds: float

&#x20;   chunk\_file\_sizes\_kb: list\[int]



class ChunkProcessingStartedEvent(BaseEvent):

&#x20;   event\_type: Literal\["CHUNK\_PROCESSING\_STARTED"]

&#x20;   chunk\_index: int

&#x20;   total\_chunks: int

&#x20;   progress\_percent: float



class ChunkTranscribedEvent(BaseEvent):

&#x20;   event\_type: Literal\["CHUNK\_TRANSCRIBED"]

&#x20;   chunk\_index: int

&#x20;   total\_chunks: int

&#x20;   preview: Annotated\[str, Field(max\_length=200)]

&#x20;   confidence: Annotated\[float, Field(ge=0.0, le=1.0)]

&#x20;   detected\_languages: list\[str]

&#x20;   issues: list\[str]

&#x20;   start\_time\_seconds: float



class QualityCheckedEvent(BaseEvent):

&#x20;   event\_type: Literal\["QUALITY\_CHECKED"]

&#x20;   chunk\_index: int

&#x20;   final\_score: Annotated\[float, Field(ge=0.0, le=1.0)]

&#x20;   heuristic\_score: Annotated\[float, Field(ge=0.0, le=1.0)]

&#x20;   ai\_score: Optional\[Annotated\[float, Field(ge=0.0, le=1.0)]]

&#x20;   recommendation: Literal\["accept", "retry", "flag"]

&#x20;   issues: list\[str]



class ChunkRetryEvent(BaseEvent):

&#x20;   event\_type: Literal\["CHUNK\_RETRY"]

&#x20;   chunk\_index: int

&#x20;   attempt: int

&#x20;   reason: str



class StitchingStartedEvent(BaseEvent):

&#x20;   event\_type: Literal\["STITCHING\_STARTED"]

&#x20;   total\_chunks: int



class StitchingCompleteEvent(BaseEvent):

&#x20;   event\_type: Literal\["STITCHING\_COMPLETE"]

&#x20;   speaker\_map: dict\[str, str]

&#x20;   speaker\_count: int

&#x20;   transcript\_preview\_lines: list\[str]   # First 5 complete lines

&#x20;   low\_confidence\_section\_count: int



class JobCompleteEvent(BaseEvent):

&#x20;   event\_type: Literal\["JOB\_COMPLETE"]

&#x20;   job\_id: str

&#x20;   speaker\_count: int

&#x20;   total\_duration\_seconds: float

&#x20;   processing\_time\_seconds: float

&#x20;   overall\_confidence: Annotated\[float, Field(ge=0.0, le=1.0)]

&#x20;   low\_confidence\_sections: int

&#x20;   languages\_detected: list\[str]

&#x20;   word\_count: int

&#x20;   # transcript\_url NOT included: frontend constructs from known base URL



class JobFailedEvent(BaseEvent):

&#x20;   event\_type: Literal\["JOB\_FAILED"]

&#x20;   error\_code: Literal\[

&#x20;       "INVALID\_AUDIO",

&#x20;       "AUDIO\_TOO\_LONG",

&#x20;       "TRANSCRIPTION\_FAILED",

&#x20;       "QUALITY\_TOO\_LOW",

&#x20;       "STORAGE\_ERROR",

&#x20;       "INTERNAL\_ERROR"

&#x20;   ]

&#x20;   error\_message: str

&#x20;   suggested\_action: Literal\[

&#x20;       "retry\_upload",

&#x20;       "check\_audio\_format",

&#x20;       "split\_file",

&#x20;       "contact\_support"

&#x20;   ]



class AgentDecisionEvent(BaseEvent):

&#x20;   event\_type: Literal\["AGENT\_DECISION"]

&#x20;   agent: str

&#x20;   decision: str

&#x20;   reason: str



class ProgressHeartbeatEvent(BaseEvent):

&#x20;   event\_type: Literal\["PROGRESS\_HEARTBEAT"]

&#x20;   overall\_progress\_percent: float

&#x20;   current\_stage: Literal\[

&#x20;       "ANALYZING", "PLANNING", "CHUNKING",

&#x20;       "TRANSCRIBING", "QUALITY\_CHECKING", "STITCHING", "FINALIZING"

&#x20;   ]

&#x20;   active\_chunk\_indexes: list\[int]

&#x20;   elapsed\_seconds: float



\# Type alias for use in type hints throughout the codebase

AnyEvent = (

&#x20;   JobAcceptedEvent | AudioAnalyzedEvent | PlanCreatedEvent |

&#x20;   ChunkingStartedEvent | ChunkingCompleteEvent |

&#x20;   ChunkProcessingStartedEvent | ChunkTranscribedEvent |

&#x20;   QualityCheckedEvent | ChunkRetryEvent | StitchingStartedEvent |

&#x20;   StitchingCompleteEvent | JobCompleteEvent | JobFailedEvent |

&#x20;   AgentDecisionEvent | ProgressHeartbeatEvent

)



── models/agent\_state.py ───────────────────────────────────────────────



Define fully typed dataclasses for agent inputs and outputs:



&#x20; AudioAnalysis:         duration\_seconds, sample\_rate, channels, 

&#x20;                        codec, bitrate\_kbps, is\_stereo, warnings

&#x20; 

&#x20; ChunkPlan:             chunk\_paths, strategy, estimated\_minutes,

&#x20;                        chunk\_duration\_seconds

&#x20; 

&#x20; TranscriptionInput:    chunk\_path, chunk\_index, total\_chunks,

&#x20;                        language\_hint, num\_speakers

&#x20; 

&#x20; TranscriptionMetadata: detected\_languages, speaker\_count,

&#x20;                        confidence, issues

&#x20; 

&#x20; TranscriptionOutput:   transcript, metadata, chunk\_index

&#x20; 

&#x20; QualityInput:          transcript, chunk\_index, 

&#x20;                        transcription\_metadata

&#x20; 

&#x20; QualityOutput:         final\_score, heuristic\_score, ai\_score,

&#x20;                        recommendation, issues

&#x20; 

&#x20; StitcherInput:         corrected\_chunks, low\_confidence\_indexes,

&#x20;                        num\_speakers, total\_duration\_seconds

&#x20; 

&#x20; StitcherOutput:        transcript, speaker\_map, word\_count,

&#x20;                        languages\_detected



── services/event\_bus.py ───────────────────────────────────────────────



Implement `EventBus` singleton class:



&#x20; Internal state:

&#x20;   \_channels: dict\[str, asyncio.Queue\[AnyEvent | None]]

&#x20;   \_sequence\_counters: dict\[str, int]

&#x20;   \_event\_history: dict\[str, list\[AnyEvent]]  # For reconnection replay

&#x20;   \_lock: asyncio.Lock



&#x20; `async def create\_channel(job\_id: str) -> None`

&#x20; 

&#x20; `async def publish(job\_id: str, event: AnyEvent) -> None`:

&#x20;   - Auto-increment sequence counter for job.

&#x20;   - Assign sequence to event.

&#x20;   - Append to \_event\_history\[job\_id] (capped at WS\_MAX\_RECONNECT\_HISTORY).

&#x20;   - Put on queue.

&#x20;   - Log at DEBUG via structlog.

&#x20; 

&#x20; `async def subscribe(job\_id: str) -> AsyncGenerator\[AnyEvent, None]`:

&#x20;   - Yield events from queue.

&#x20;   - Yield None sentinel when JOB\_COMPLETE or JOB\_FAILED received.

&#x20;   - Raise KeyError if channel not found.

&#x20; 

&#x20; `async def replay\_history(job\_id: str, from\_sequence: int) -> list\[AnyEvent]`:

&#x20;   - Return all events with sequence > from\_sequence.

&#x20;   - Used when a WebSocket client reconnects after a drop.

&#x20; 

&#x20; `async def destroy\_channel(job\_id: str) -> None`:

&#x20;   - Put None sentinel on queue.

&#x20;   - Remove from all dicts.

&#x20; 

&#x20; `def get\_instance() -> EventBus`:

&#x20;   - Module-level singleton accessor.



── core/connection\_manager.py ──────────────────────────────────────────



Implement `ConnectionManager` singleton class:



&#x20; `async def connect(job\_id, ws, last\_sequence: int = 0) -> None`:

&#x20;   - ws.accept()

&#x20;   - Register in dict\[job\_id → set\[WebSocket]]

&#x20;   - If last\_sequence > 0: immediately replay missed events via

&#x20;     event\_bus.replay\_history() and send them to this socket only.

&#x20;   

&#x20; `async def disconnect(job\_id, ws) -> None`

&#x20; 

&#x20; `async def broadcast\_to\_job(job\_id, event: AnyEvent) -> None`:

&#x20;   - Serialize event with event.model\_dump\_json()

&#x20;   - Send to all sockets for job\_id

&#x20;   - Handle each socket send in try/except

&#x20;   - On send failure: disconnect that socket, continue others

&#x20; 

&#x20; `def get\_active\_connection\_count(job\_id: str) -> int`



── tests/test\_events.py ────────────────────────────────────────────────



Generate tests for:

&#x20; - Every event class serializes to valid JSON

&#x20; - Sequence numbers auto-increment correctly per job

&#x20; - Event replay returns only events after from\_sequence

&#x20; - Sentinel None correctly ends async generator

&#x20; - AnyEvent union type accepts all defined event types

&#x20; - schema\_version field present on all events

&#x20; - Field constraints enforced (confidence 0-1, max\_length on preview)



══════════════════════════════════════════════════════════════════════════

PHASE 4 — AUDIO PROCESSING

Files: services/audio\_processor.py, tests/test\_audio\_processor.py

══════════════════════════════════════════════════════════════════════════



── services/audio\_processor.py ─────────────────────────────────────────



Define `AudioProcessingError(Exception)` with fields:

&#x20; message: str, ffmpeg\_stderr: Optional\[str], returncode: Optional\[int]



`async def analyze\_audio(input\_path: Path) -> AudioAnalysis`:

&#x20; - Run ffprobe via asyncio.create\_subprocess\_exec (NEVER shell=True):

&#x20;   args = \[

&#x20;     "ffprobe", "-v", "quiet",

&#x20;     "-print\_format", "json",

&#x20;     "-show\_streams", "-show\_format",

&#x20;     str(input\_path)

&#x20;   ]

&#x20; - Parse JSON stdout into AudioAnalysis dataclass.

&#x20; - Extract: duration, sample\_rate, channels, codec\_name, bit\_rate.

&#x20; - Set bitrate\_kbps = None if bit\_rate is "N/A" or "0" (VBR case).

&#x20; - Build quality\_warnings list:

&#x20;     \* sample\_rate < 8000  → "Very low sample rate ({n}Hz). 

&#x20;                              Accuracy may be significantly reduced."

&#x20;     \* sample\_rate < 16000 → "Low sample rate ({n}Hz). 

&#x20;                              Consider using 16kHz+ audio for best results."

&#x20;     \* channels > 2        → "Multi-channel audio detected. 

&#x20;                              Converting to mono for processing."

&#x20;     \* duration > 3600     → "Audio exceeds 1 hour. 

&#x20;                              Processing will take approximately {n} minutes."

&#x20;     \* duration > MAX\_AUDIO\_DURATION\_SECONDS → raise AudioProcessingError

&#x20; - Return AudioAnalysis.



`async def chunk\_audio(

&#x20;   input\_path: Path, 

&#x20;   job\_id: str,

&#x20;   analysis: AudioAnalysis

) -> list\[Path]`:

&#x20; - Create output directory: CHUNKS\_DIR / job\_id

&#x20; - Build ffmpeg args as explicit list (NO shell=True, EVER):

&#x20;   \[

&#x20;     "ffmpeg", "-i", str(input\_path),

&#x20;     "-f", "segment",

&#x20;     "-segment\_time", str(CHUNK\_DURATION\_SECONDS),

&#x20;     "-c:a", "libmp3lame",

&#x20;     "-q:a", "4",

&#x20;     "-ar", "16000",

&#x20;     "-ac", "1",            # Mono — reduces cost + improves accuracy

&#x20;     "-reset\_timestamps", "1",

&#x20;     "-loglevel", "error",  # Suppress ffmpeg banner noise

&#x20;     str(output\_dir / "chunk\_%04d.mp3")

&#x20;   ]

&#x20; - Run via asyncio.create\_subprocess\_exec.

&#x20; - Capture stderr. On returncode != 0: raise AudioProcessingError.

&#x20; - Glob output\_dir for "chunk\_\*.mp3", sort by name.

&#x20; - Validate at least 1 chunk produced.

&#x20; - Return sorted list of Paths.



══════════════════════════════════════════════════════════════════════════

PHASE 5 — AGENTIC CORE

Files: agents/base\_agent.py, agents/orchestrator.py,

&#x20;      agents/transcription\_agent.py, agents/quality\_agent.py,

&#x20;      agents/stitcher\_agent.py, utils/timestamp\_math.py,

&#x20;      tests/test\_agents.py, tests/test\_timestamp\_math.py

══════════════════════════════════════════════════════════════════════════



── agents/base\_agent.py ────────────────────────────────────────────────



Abstract base class:



class BaseAgent(ABC):

&#x20;   def \_\_init\_\_(self, job\_id: str, event\_bus: EventBus, settings: Settings):

&#x20;       self.job\_id = job\_id

&#x20;       self.event\_bus = event\_bus

&#x20;       self.settings = settings

&#x20;       self.\_sequence = 0

&#x20;       self.logger = structlog.get\_logger().bind(

&#x20;           agent=self.\_\_class\_\_.\_\_name\_\_,

&#x20;           job\_id=job\_id

&#x20;       )



&#x20;   @abstractmethod

&#x20;   async def run(self, input: Any) -> Any: ...



&#x20;   async def emit(self, event: AnyEvent) -> None:

&#x20;       """Central emit: publish to event bus, which fans out to WebSocket."""

&#x20;       await self.event\_bus.publish(self.job\_id, event)

&#x20;       self.logger.debug("event\_emitted", event\_type=event.event\_type)



&#x20;   def \_make\_event(self, event\_class: type, \*\*kwargs) -> AnyEvent:

&#x20;       """Factory: injects job\_id and timestamp automatically."""

&#x20;       return event\_class(

&#x20;           job\_id=self.job\_id,

&#x20;           timestamp=datetime.utcnow(),

&#x20;           sequence=0,   # EventBus assigns real sequence on publish

&#x20;           \*\*kwargs

&#x20;       )



── agents/transcription\_agent.py ───────────────────────────────────────



SYSTEM PROMPT (verbatim — do not alter, this is the 97% accuracy prompt):

"""

You are AuraScript's expert transcription engine, specializing in 

Manglish — the natural, fluid code-switching between English and 

Southeast Asian languages including:

&#x20; - Bahasa Malaysia / Bahasa Indonesia

&#x20; - Mandarin Chinese (and regional variants)

&#x20; - Cantonese

&#x20; - Hokkien / Hakka / Teochew

&#x20; - Tamil

&#x20; - Tagalog



YOUR ABSOLUTE RULES:



1\. VERBATIM ACCURACY

&#x20;  Transcribe EXACTLY what is spoken. Every word, every syllable.

&#x20;  Preserve natural speech patterns including fillers: 

&#x20;  "lah", "mah", "lor", "wor", "kan", "leh", "ah", "oh", "wah".



2\. ZERO TRANSLATION

&#x20;  NEVER convert native language words to English equivalents.

&#x20;  If the speaker says "makan", write "makan". Not "eat".

&#x20;  If the speaker says "pergi", write "pergi". Not "go".



3\. PHONETIC PRESERVATION

&#x20;  For unclear native words, transcribe the exact phonetics you hear.

&#x20;  Do NOT substitute a more familiar word.



4\. UNCERTAINTY HANDLING

&#x20;  Unclear audio → \[inaudible]

&#x20;  Cut-off word at chunk end → write partial syllables + \[cut-off]

&#x20;  Overlapping speech → transcribe what is most audible, add \[overlap]



5\. FORMAT — STRICT, NO DEVIATION

&#x20;  Every speaker turn must follow this exact format:

&#x20;  \[MM:SS] \[Speaker X]: <verbatim text>

&#x20;  

&#x20;  - Timestamps are RELATIVE to THIS chunk, starting at \[00:00]

&#x20;  - New timestamp on every speaker change

&#x20;  - New timestamp every 30 seconds if same speaker continues

&#x20;  - Speakers labeled A, B, C... in order of first appearance



6\. BACKGROUND ANNOTATION

&#x20;  Non-speech sounds that affect comprehension:

&#x20;  \[background: description] — e.g. \[background: loud traffic]

&#x20;  \[laughter], \[pause], \[crosstalk]



7\. METADATA BLOCK (MANDATORY — append to EVERY response)

&#x20;  ---METADATA---

&#x20;  detected\_languages: \[comma-separated list]

&#x20;  speaker\_count: <integer>

&#x20;  confidence: <float 0.0-1.0>

&#x20;  issues: \[comma-separated: audio\_cutoff|noise|overlap|low\_quality|none]

&#x20;  ---END METADATA---



{language\_hint\_instruction}

Expected speakers in this chunk: {num\_speakers}

"""



Where:

&#x20; language\_hint\_instruction = 

&#x20;   f"Primary language hint: {language\_hint}. Prioritize this language's 

&#x20;   phonetics when audio is ambiguous." 

&#x20;   if language\_hint else ""



generation\_config:

&#x20; temperature=0.0    # Deterministic — critical for accuracy

&#x20; max\_output\_tokens=8192

&#x20; top\_p=1.0

&#x20; top\_k=1



safety\_settings: BLOCK\_NONE for all categories

&#x20; (transcription of real conversation requires unfiltered output)



Tenacity retry on TranscriptionAgent:

&#x20; @retry(

&#x20;   stop=stop\_after\_attempt(3),

&#x20;   wait=wait\_exponential(multiplier=1, min=2, max=30),

&#x20;   retry=retry\_if\_exception\_type((

&#x20;       google.api\_core.exceptions.ResourceExhausted,

&#x20;       google.api\_core.exceptions.ServiceUnavailable,

&#x20;       google.api\_core.exceptions.DeadlineExceeded,

&#x20;   )),

&#x20;   before\_sleep=before\_sleep\_log(logger, logging.WARNING)

&#x20; )



After response, parse ---METADATA--- block with regex.

On parse failure: use default TranscriptionMetadata with 

&#x20; confidence=0.5, issues=\["metadata\_parse\_failed"].

NEVER crash on metadata parse failure.



── agents/quality\_agent.py ─────────────────────────────────────────────



HEURISTIC CHECKS (no API call, run always):



&#x20; def \_compute\_heuristic\_score(transcript: str, chunk\_index: int, 

&#x20;                               total\_chunks: int, 

&#x20;                               metadata: TranscriptionMetadata) -> float:

&#x20;   score = 1.0

&#x20;   word\_count = len(transcript.split())

&#x20;   

&#x20;   # Penalty: too few words for 3-minute chunk

&#x20;   if word\_count < 30:

&#x20;     score -= 0.4

&#x20;   elif word\_count < 60:

&#x20;     score -= 0.2

&#x20;   

&#x20;   # Penalty: excessive inaudible markers

&#x20;   inaudible\_count = transcript.count("\[inaudible]")

&#x20;   inaudible\_ratio = inaudible\_count / max(word\_count, 1)

&#x20;   if inaudible\_ratio > 0.2:

&#x20;     score -= 0.3

&#x20;   elif inaudible\_ratio > 0.1:

&#x20;     score -= 0.1

&#x20;   

&#x20;   # Penalty: cut-off not at last chunk (unexpected)

&#x20;   cutoff\_count = transcript.count("\[cut-off]")

&#x20;   is\_last\_chunk = (chunk\_index == total\_chunks - 1)

&#x20;   if cutoff\_count > 0 and not is\_last\_chunk:

&#x20;     score -= 0.15

&#x20;   

&#x20;   # Penalty: missing timestamps entirely

&#x20;   timestamp\_count = len(re.findall(r'\\\[\\d{2}:\\d{2}\\]', transcript))

&#x20;   if timestamp\_count == 0:

&#x20;     score -= 0.3

&#x20;   

&#x20;   # Incorporate AI confidence from metadata

&#x20;   score = (score \* 0.5) + (metadata.confidence \* 0.5)

&#x20;   

&#x20;   return max(0.0, min(1.0, score))



AI VALIDATION (only if heuristic\_score < 0.7):



&#x20; Prompt to Gemini Flash:

&#x20; """

&#x20; Review this Manglish transcript chunk for transcription quality.

&#x20; 

&#x20; Penalize:

&#x20; - Invented words not matching Manglish phonetics

&#x20; - Missing speaker changes

&#x20; - Timestamp format errors  

&#x20; - Signs of hallucination (words that couldn't have been spoken)

&#x20; - English translations where native words should appear

&#x20; 

&#x20; Respond in STRICT JSON, no other text:

&#x20; {"score": <float 0.0-1.0>, "issues": \[<strings>], 

&#x20;  "recommendation": "<accept|retry|flag>"}

&#x20; """



&#x20; On JSON parse failure: log warning, default to 

&#x20;   {"score": 0.7, "issues": \[], "recommendation": "accept"}



Final score formula:

&#x20; If AI check ran:    (heuristic \* 0.4) + (ai\_score \* 0.6)

&#x20; If AI skipped:      heuristic\_score



── agents/stitcher\_agent.py ────────────────────────────────────────────



STITCHING SYSTEM PROMPT (verbatim):

"""

You are AuraScript's transcript unification engine.



INPUT: A Manglish transcript assembled from sequential audio chunks.

Chunks are separated by '--- CHUNK BOUNDARY ---'.

Sections marked with ⚠️ LOW CONFIDENCE were flagged during quality checks.



YOUR TASKS — execute in this exact order:



TASK 1: GLOBAL SPEAKER UNIFICATION

&#x20; Speaker labels reset at every chunk boundary. The same person may be

&#x20; called \[Speaker A] in chunk 1 and \[Speaker B] in chunk 2.

&#x20; 

&#x20; Analyze:

&#x20; - Conversation context and topic continuity

&#x20; - Speaking style, vocabulary, and language preferences

&#x20; - Turn-taking patterns around chunk boundaries

&#x20; 

&#x20; Assign globally consistent labels: \[Speaker 1], \[Speaker 2], etc.

&#x20; If you genuinely cannot identify a speaker, use \[Speaker ?].

&#x20; NEVER guess. Uncertainty is better than a wrong label.



TASK 2: BOUNDARY WORD REPAIR

&#x20; Find all \[cut-off] markers.

&#x20; Look at the immediately following chunk for context.

&#x20; If you can reconstruct the word with confidence: complete it.

&#x20; If not: replace with \[inaudible].

&#x20; 

TASK 3: OUTPUT CLEANUP

&#x20; Remove all '--- CHUNK BOUNDARY ---' markers.

&#x20; Remove all ⚠️ LOW CONFIDENCE warning lines.

&#x20; Keep ALL timestamps exactly as-is (do not alter any timestamp).

&#x20; Keep ALL native language words exactly as-is (no translation).

&#x20; Do NOT add, remove, paraphrase, or summarize ANY content.



TASK 4: FINAL FORMAT

&#x20; \[MM:SS] \[Speaker N]: <verbatim text>

&#x20; Use \[HH:MM:SS] if total duration exceeds 60 minutes.



TASK 5: JSON OUTPUT (mandatory)

&#x20; Respond with ONLY this JSON object, no other text:

&#x20; {

&#x20;   "transcript": "<complete unified transcript>",

&#x20;   "speaker\_map": {

&#x20;     "Speaker 1": "<description or 'unknown'>",

&#x20;     "Speaker 2": "<description or 'unknown'>"

&#x20;   },

&#x20;   "word\_count": <integer>,

&#x20;   "languages\_detected": \["<lang1>", "<lang2>"]

&#x20; }



Expected number of unique speakers: {num\_speakers}

"""



On JSON parse failure:

&#x20; - Extract raw text between first { and last } with regex

&#x20; - If still fails: use raw response as transcript, empty speaker\_map

&#x20; - Log the parse failure with the raw response

&#x20; - Never crash the pipeline on a JSON parse error



── utils/timestamp\_math.py ─────────────────────────────────────────────



`def fix\_chunk\_timestamps(

&#x20;   raw\_transcript: str,

&#x20;   chunk\_index: int,

&#x20;   chunk\_duration\_seconds: int

) -> str`:



&#x20; offset\_seconds = chunk\_index \* chunk\_duration\_seconds

&#x20; 

&#x20; Use re.sub with replacement function:

&#x20;   pattern = r'\\\[(\\d{2}):(\\d{2})\\]'

&#x20;   

&#x20;   For each match:

&#x20;     chunk\_mm = int(match.group(1))

&#x20;     chunk\_ss = int(match.group(2))

&#x20;     total\_seconds = (chunk\_mm \* 60) + chunk\_ss + offset\_seconds

&#x20;     

&#x20;     # Handle durations over 1 hour correctly

&#x20;     hours = total\_seconds // 3600

&#x20;     minutes = (total\_seconds % 3600) // 60

&#x20;     seconds = total\_seconds % 60

&#x20;     

&#x20;     if hours > 0:

&#x20;         return f"\[{hours:02d}:{minutes:02d}:{seconds:02d}]"

&#x20;     else:

&#x20;         return f"\[{minutes:02d}:{seconds:02d}]"

&#x20; 

&#x20; Return corrected transcript string.



── agents/orchestrator.py ──────────────────────────────────────────────



This is the master agent. It directs all other agents.

It NEVER calls Gemini directly — it delegates to specialist agents.



`async def run(self, input: OrchestratorInput) -> OrchestratorOutput`:



&#x20; job\_start\_time = time.monotonic()

&#x20; all\_file\_paths: list\[Path] = \[input.audio\_path]



&#x20; try:

&#x20;   # ── STAGE 1: ANALYZE ────────────────────────────────────────────

&#x20;   await self.emit(self.\_make\_event(ProgressHeartbeatEvent,

&#x20;     overall\_progress\_percent=2.0, current\_stage="ANALYZING",

&#x20;     active\_chunk\_indexes=\[], elapsed\_seconds=0.0))

&#x20;   

&#x20;   analysis = await analyze\_audio(input.audio\_path)

&#x20;   

&#x20;   await self.emit(self.\_make\_event(AudioAnalyzedEvent, 

&#x20;     duration\_seconds=analysis.duration\_seconds, ...))

&#x20;   await self.emit(self.\_make\_event(AgentDecisionEvent,

&#x20;     agent="Orchestrator",

&#x20;     decision=f"Audio analyzed: {analysis.duration\_seconds:.0f}s, 

&#x20;              {analysis.codec}, {analysis.sample\_rate}Hz",

&#x20;     reason="ffprobe analysis complete"))



&#x20;   # ── STAGE 2: PLAN ───────────────────────────────────────────────

&#x20;   estimated\_chunks = math.ceil(

&#x20;     analysis.duration\_seconds / settings.CHUNK\_DURATION\_SECONDS)

&#x20;   strategy = ("single\_chunk" if estimated\_chunks == 1

&#x20;                else "large\_file\_warning" if 

&#x20;                  analysis.duration\_seconds > 3600

&#x20;                else "multi\_chunk")

&#x20;   estimated\_minutes = (estimated\_chunks \* 25) / 60  

&#x20;   # \~25 seconds per chunk is empirical Gemini Pro estimate

&#x20;   

&#x20;   await self.emit(self.\_make\_event(PlanCreatedEvent, 

&#x20;     estimated\_chunks=estimated\_chunks, strategy=strategy,

&#x20;     estimated\_processing\_minutes=estimated\_minutes,

&#x20;     chunk\_duration\_seconds=settings.CHUNK\_DURATION\_SECONDS))



&#x20;   # ── STAGE 3: CHUNK ──────────────────────────────────────────────

&#x20;   await self.emit(self.\_make\_event(ChunkingStartedEvent,

&#x20;     total\_expected\_chunks=estimated\_chunks))

&#x20;   

&#x20;   chunk\_paths = await chunk\_audio(input.audio\_path, 

&#x20;                                    self.job\_id, analysis)

&#x20;   all\_file\_paths.extend(chunk\_paths)

&#x20;   

&#x20;   await self.emit(self.\_make\_event(ChunkingCompleteEvent,

&#x20;     actual\_chunk\_count=len(chunk\_paths),

&#x20;     total\_audio\_seconds=analysis.duration\_seconds,

&#x20;     chunk\_file\_sizes\_kb=\[int(p.stat().st\_size/1024) 

&#x20;                          for p in chunk\_paths]))



&#x20;   # ── STAGE 4: TRANSCRIBE (PARALLEL) ──────────────────────────────

&#x20;   semaphore = asyncio.Semaphore(settings.MAX\_CONCURRENT\_GEMINI\_CALLS)

&#x20;   heartbeat\_task = asyncio.create\_task(

&#x20;     self.\_heartbeat\_loop("TRANSCRIBING", job\_start\_time))

&#x20;   

&#x20;   tasks = \[

&#x20;     TranscriptionAgent(self.job\_id, self.event\_bus, self.settings)

&#x20;       .run(TranscriptionInput(

&#x20;         chunk\_path=path, chunk\_index=i,

&#x20;         total\_chunks=len(chunk\_paths),

&#x20;         language\_hint=input.language\_hint,

&#x20;         num\_speakers=input.num\_speakers,

&#x20;         semaphore=semaphore))

&#x20;     for i, path in enumerate(chunk\_paths)

&#x20;   ]

&#x20;   

&#x20;   results = await asyncio.gather(\*tasks, return\_exceptions=True)

&#x20;   heartbeat\_task.cancel()

&#x20;   

&#x20;   # Handle partial failures gracefully

&#x20;   transcription\_outputs: list\[TranscriptionOutput] = \[]

&#x20;   for i, result in enumerate(results):

&#x20;     if isinstance(result, Exception):

&#x20;       self.logger.error("chunk\_transcription\_failed", 

&#x20;                         chunk\_index=i, error=str(result))

&#x20;       transcription\_outputs.append(TranscriptionOutput(

&#x20;         transcript=f"\[TRANSCRIPTION\_ERROR: chunk {i} failed]",

&#x20;         metadata=TranscriptionMetadata(confidence=0.0,

&#x20;           issues=\["agent\_exception"]),

&#x20;         chunk\_index=i))

&#x20;     else:

&#x20;       transcription\_outputs.append(result)

&#x20;   

&#x20;   # Sort by chunk\_index (gather does not guarantee order)

&#x20;   transcription\_outputs.sort(key=lambda x: x.chunk\_index)



&#x20;   # ── STAGE 5: QUALITY CHECK (PARALLEL) ───────────────────────────

&#x20;   quality\_tasks = \[

&#x20;     QualityAgent(self.job\_id, self.event\_bus, self.settings)

&#x20;       .run(QualityInput(

&#x20;         transcript=output.transcript,

&#x20;         chunk\_index=output.chunk\_index,

&#x20;         total\_chunks=len(chunk\_paths),

&#x20;         transcription\_metadata=output.metadata))

&#x20;     for output in transcription\_outputs

&#x20;   ]

&#x20;   quality\_results = await asyncio.gather(\*quality\_tasks, 

&#x20;                                           return\_exceptions=True)



&#x20;   # ── STAGE 6: RETRY LOGIC ────────────────────────────────────────

&#x20;   final\_transcripts: list\[str] = \[]

&#x20;   low\_confidence\_indexes: list\[int] = \[]

&#x20;   

&#x20;   for i, (output, quality) in enumerate(

&#x20;       zip(transcription\_outputs, quality\_results)):

&#x20;     

&#x20;     if isinstance(quality, Exception):

&#x20;       # Quality check itself failed — accept the transcript

&#x20;       final\_transcripts.append(output.transcript)

&#x20;       continue

&#x20;     

&#x20;     if quality.recommendation == "retry":

&#x20;       await self.emit(self.\_make\_event(ChunkRetryEvent,

&#x20;         chunk\_index=i, attempt=1, reason=str(quality.issues)))

&#x20;       

&#x20;       # Retry once with modified prompt

&#x20;       retry\_result = await TranscriptionAgent(

&#x20;         self.job\_id, self.event\_bus, self.settings

&#x20;       ).run(TranscriptionInput(..., is\_retry=True))

&#x20;       

&#x20;       retry\_quality = await QualityAgent(...).run(

&#x20;         QualityInput(transcript=retry\_result.transcript, ...))

&#x20;       

&#x20;       if retry\_quality.final\_score >= settings.LOW\_CONFIDENCE\_THRESHOLD:

&#x20;         final\_transcripts.append(retry\_result.transcript)

&#x20;       else:

&#x20;         low\_confidence\_indexes.append(i)

&#x20;         final\_transcripts.append(

&#x20;           f"⚠️ \[LOW CONFIDENCE SECTION]\\n{retry\_result.transcript}")

&#x20;     

&#x20;     elif quality.recommendation == "flag":

&#x20;       low\_confidence\_indexes.append(i)

&#x20;       final\_transcripts.append(

&#x20;         f"⚠️ \[LOW CONFIDENCE SECTION]\\n{output.transcript}")

&#x20;     

&#x20;     else:  # "accept"

&#x20;       final\_transcripts.append(output.transcript)



&#x20;   # ── STAGE 7: TIMESTAMP CORRECTION ───────────────────────────────

&#x20;   corrected\_transcripts = \[

&#x20;     fix\_chunk\_timestamps(t, i, settings.CHUNK\_DURATION\_SECONDS)

&#x20;     for i, t in enumerate(final\_transcripts)

&#x20;   ]



&#x20;   # ── STAGE 8: STITCH ─────────────────────────────────────────────

&#x20;   if len(corrected\_transcripts) == 1:

&#x20;     # Skip stitching for single chunk — save API cost

&#x20;     final\_transcript = corrected\_transcripts\[0]

&#x20;     speaker\_map = {}

&#x20;     await self.emit(self.\_make\_event(AgentDecisionEvent,

&#x20;       agent="Orchestrator",

&#x20;       decision="Skipping stitching phase",

&#x20;       reason="Single chunk — no boundary repair or speaker 

&#x20;               unification needed. Saves API cost."))

&#x20;   else:

&#x20;     await self.emit(self.\_make\_event(StitchingStartedEvent,

&#x20;       total\_chunks=len(corrected\_transcripts)))

&#x20;     

&#x20;     stitch\_output = await StitcherAgent(

&#x20;       self.job\_id, self.event\_bus, self.settings

&#x20;     ).run(StitcherInput(

&#x20;       corrected\_chunks=corrected\_transcripts,

&#x20;       low\_confidence\_indexes=low\_confidence\_indexes,

&#x20;       num\_speakers=input.num\_speakers,

&#x20;       total\_duration\_seconds=analysis.duration\_seconds))

&#x20;     

&#x20;     final\_transcript = stitch\_output.transcript

&#x20;     speaker\_map = stitch\_output.speaker\_map



&#x20;   # ── STAGE 9: COMPLETE ───────────────────────────────────────────

&#x20;   processing\_seconds = time.monotonic() - job\_start\_time

&#x20;   overall\_confidence = sum(

&#x20;     o.metadata.confidence for o in transcription\_outputs

&#x20;   ) / len(transcription\_outputs)

&#x20;   

&#x20;   await self.emit(self.\_make\_event(JobCompleteEvent,

&#x20;     job\_id=self.job\_id,

&#x20;     speaker\_count=len(speaker\_map) or input.num\_speakers,

&#x20;     total\_duration\_seconds=analysis.duration\_seconds,

&#x20;     processing\_time\_seconds=processing\_seconds,

&#x20;     overall\_confidence=overall\_confidence,

&#x20;     low\_confidence\_sections=len(low\_confidence\_indexes),

&#x20;     languages\_detected=stitch\_output.languages\_detected 

&#x20;                        if len(corrected\_transcripts) > 1 

&#x20;                        else transcription\_outputs\[0].metadata.detected\_languages,

&#x20;     word\_count=stitch\_output.word\_count 

&#x20;                if len(corrected\_transcripts) > 1

&#x20;                else len(final\_transcript.split())))

&#x20;   

&#x20;   return OrchestratorOutput(

&#x20;     transcript=final\_transcript,

&#x20;     speaker\_map=speaker\_map,

&#x20;     metadata={...})



&#x20; except Exception as e:

&#x20;   # Map exception types to typed error codes

&#x20;   error\_code = self.\_classify\_error(e)

&#x20;   await self.emit(self.\_make\_event(JobFailedEvent,

&#x20;     error\_code=error\_code,

&#x20;     error\_message=self.\_safe\_error\_message(error\_code),

&#x20;     suggested\_action=self.\_suggest\_action(error\_code)))

&#x20;   raise



&#x20; finally:

&#x20;   # ALWAYS clean up — success or failure

&#x20;   await cleanup\_job\_files(all\_file\_paths)



&#x20; async def \_heartbeat\_loop(self, stage: str, 

&#x20;                            start\_time: float) -> None:

&#x20;   """Emit heartbeat every 5s to prevent frontend frozen UI."""

&#x20;   while True:

&#x20;     await asyncio.sleep(5)

&#x20;     await self.emit(self.\_make\_event(ProgressHeartbeatEvent,

&#x20;       overall\_progress\_percent=self.\_current\_progress,

&#x20;       current\_stage=stage,

&#x20;       active\_chunk\_indexes=self.\_active\_chunks,

&#x20;       elapsed\_seconds=time.monotonic() - start\_time))



&#x20; def \_classify\_error(self, e: Exception) -> str:

&#x20;   # Maps Python exceptions to safe error codes

&#x20;   if isinstance(e, AudioProcessingError):

&#x20;     return "INVALID\_AUDIO"

&#x20;   if isinstance(e, ResourceExhausted):

&#x20;     return "TRANSCRIPTION\_FAILED"

&#x20;   if isinstance(e, IOError):

&#x20;     return "STORAGE\_ERROR"

&#x20;   return "INTERNAL\_ERROR"



&#x20; def \_safe\_error\_message(self, error\_code: str) -> str:

&#x20;   # Human-friendly messages. NEVER expose internal details.

&#x20;   messages = {

&#x20;     "INVALID\_AUDIO": "The audio file could not be processed. 

&#x20;                       Please check the file format.",

&#x20;     "AUDIO\_TOO\_LONG": "Audio exceeds the 2-hour maximum. 

&#x20;                        Please split into shorter segments.",

&#x20;     "TRANSCRIPTION\_FAILED": "The transcription service encountered 

&#x20;                               an error. Please try again.",

&#x20;     "QUALITY\_TOO\_LOW": "Audio quality was too low to transcribe 

&#x20;                         accurately.",

&#x20;     "STORAGE\_ERROR": "A storage error occurred. Please try again.",

&#x20;     "INTERNAL\_ERROR": "An unexpected error occurred. 

&#x20;                        Contact support if this persists."

&#x20;   }

&#x20;   return messages.get(error\_code, messages\["INTERNAL\_ERROR"])



══════════════════════════════════════════════════════════════════════════

PHASE 6 — API LAYER

Files: routers/transcription.py, routers/websocket.py, routers/health.py,

&#x20;      models/schemas.py, services/webhook\_service.py,

&#x20;      services/pipeline.py, main.py, dependencies.py

══════════════════════════════════════════════════════════════════════════



── models/schemas.py ───────────────────────────────────────────────────



HTTP request and response models (separate from WebSocket events):



class TranscribeRequest(BaseModel):

&#x20; language\_hint: str = Field("auto", max\_length=50)

&#x20; num\_speakers: Annotated\[int, Field(ge=1, le=10)] = 2

&#x20; webhook\_url: Optional\[HttpUrl] = None



class TranscribeResponse(BaseModel):

&#x20; job\_id: str

&#x20; status: str

&#x20; websocket\_url: str    # wss://www.aurascript.au/ws/transcribe/{id}?token=

&#x20; poll\_url: str         # https://www.aurascript.au/transcribe/status/{id}

&#x20; result\_url: str       # https://www.aurascript.au/transcribe/result/{id}

&#x20; message: str



class JobStatusResponse(BaseModel):

&#x20; job\_id: str

&#x20; status: str

&#x20; progress\_percent: float

&#x20; current\_stage: str

&#x20; created\_at: datetime

&#x20; updated\_at: datetime

&#x20; estimated\_completion\_seconds: Optional\[float]



class JobResultResponse(BaseModel):

&#x20; job\_id: str

&#x20; status: str

&#x20; transcript: str

&#x20; speaker\_map: dict\[str, str]

&#x20; metadata: dict



class HealthResponse(BaseModel):

&#x20; status: str

&#x20; version: str

&#x20; environment: str

&#x20; vertex\_ai\_status: str

&#x20; active\_jobs: int

&#x20; timestamp: datetime



── routers/transcription.py ────────────────────────────────────────────



POST /transcribe

&#x20; Dependencies: \[Depends(verify\_api\_key), Depends(rate\_limiter)]

&#x20; - Accept: multipart/form-data

&#x20;   Fields: audio\_file: UploadFile, language\_hint: str = Form("auto"),

&#x20;           num\_speakers: int = Form(2), webhook\_url: str = Form(None)

&#x20; - Validate form fields with Pydantic BEFORE touching the file.

&#x20; - Check MAX\_CONCURRENT\_JOBS limit via job\_store.

&#x20; - Save file via SafeFileStorage.

&#x20; - Create JobRecord.

&#x20; - Launch pipeline.process\_transcription\_job as BackgroundTask.

&#x20; - Return 202 TranscribeResponse with:

&#x20;   websocket\_url: f"{settings.websocket\_base\_url}/ws/transcribe/

&#x20;                    {job\_id}?token={api\_key}"

&#x20;   poll\_url: f"{settings.PRIMARY\_DOMAIN}/transcribe/status/{job\_id}"

&#x20;   result\_url: f"{settings.PRIMARY\_DOMAIN}/transcribe/result/{job\_id}"



GET /transcribe/status/{job\_id}

&#x20; - Auth required.

&#x20; - Return JobStatusResponse.

&#x20; - Estimate completion: (remaining\_chunks × 25s) + stitching\_estimate



GET /transcribe/result/{job\_id}

&#x20; - Auth required.

&#x20; - 404 if not found.

&#x20; - 202 with status if still PROCESSING.

&#x20; - 200 with JobResultResponse if COMPLETED.

&#x20; - 422 with error details if FAILED.



DELETE /transcribe/{job\_id}

&#x20; - Auth required.

&#x20; - Cancel job via job\_store.cancel\_job()

&#x20; - Trigger immediate cleanup

&#x20; - Return 200 confirmation



POST /transcribe/webhook-test

&#x20; - Auth required.

&#x20; - Body: {"webhook\_url": "https://..."}

&#x20; - Send test payload via WebhookService

&#x20; - Return delivery result with status code received



── routers/websocket.py ────────────────────────────────────────────────



@router.websocket("/ws/transcribe/{job\_id}")

async def transcription\_websocket(

&#x20;   websocket: WebSocket,

&#x20;   job\_id: str,

&#x20;   token: str = Query(...),

&#x20;   last\_sequence: int = Query(0),  # For reconnection replay

&#x20;   ...

):

&#x20; AUTHENTICATION BEFORE ACCEPT:

&#x20; - Validate token against VALID\_API\_KEYS with secrets.compare\_digest.

&#x20; - On failure: close with code 1008 WITHOUT calling ws.accept().

&#x20; 

&#x20; RECONNECTION HANDLING:

&#x20; - Check job status.

&#x20; - If COMPLETED: accept → send cached JobCompleteEvent → close 1000.

&#x20; - If FAILED: accept → send cached JobFailedEvent → close 1000.

&#x20; - If PENDING/PROCESSING with last\_sequence > 0:

&#x20;     Replay missed events from last\_sequence via replay\_history().

&#x20; 

&#x20; KEEPALIVE:

&#x20; - Launch keepalive coroutine alongside main loop.

&#x20; - Send WebSocket ping every WS\_PING\_INTERVAL\_SECONDS seconds.

&#x20; - If no pong within WS\_PING\_TIMEOUT\_SECONDS: close connection.

&#x20; 

&#x20; MAIN LOOP:

&#x20; - Subscribe to event\_bus.subscribe(job\_id).

&#x20; - For each event: connection\_manager.broadcast\_to\_job(job\_id, event).

&#x20; - On WebSocketDisconnect: log and exit cleanly.

&#x20; - On None sentinel: exit cleanly (job done).



── services/webhook\_service.py ─────────────────────────────────────────



class WebhookService:

&#x20; async def deliver(webhook\_url: str, event: AnyEvent, job\_id: str):

&#x20;   payload = event.model\_dump\_json().encode()

&#x20;   signature = hmac.new(

&#x20;     settings.WEBHOOK\_SECRET.encode(),

&#x20;     payload,

&#x20;     hashlib.sha256

&#x20;   ).hexdigest()

&#x20;   

&#x20;   headers = {

&#x20;     "Content-Type": "application/json",

&#x20;     "X-AuraScript-Job-ID": job\_id,

&#x20;     "X-AuraScript-Event-Type": event.event\_type,

&#x20;     "X-AuraScript-Signature": f"sha256={signature}",

&#x20;     "X-AuraScript-Schema-Version": "1.1",

&#x20;     "User-Agent": "AuraScript-Webhook/1.0"

&#x20;   }

&#x20;   

&#x20;   Retry: 3 attempts, delays \[5, 15, 30] seconds.

&#x20;   Use httpx.AsyncClient, timeout=10s.

&#x20;   Fire-and-forget via asyncio.create\_task (non-blocking).

&#x20;   Log all attempts and response status codes.



── main.py ─────────────────────────────────────────────────────────────



@asynccontextmanager

async def lifespan(app: FastAPI):

&#x20; # STARTUP

&#x20; settings.UPLOAD\_DIR.mkdir(parents=True, exist\_ok=True)

&#x20; settings.CHUNKS\_DIR.mkdir(parents=True, exist\_ok=True)

&#x20; 

&#x20; vertexai.init(project=settings.GOOGLE\_CLOUD\_PROJECT,

&#x20;               location=settings.GOOGLE\_CLOUD\_LOCATION)

&#x20; 

&#x20; orphans = await scan\_orphaned\_files()

&#x20; if orphans:

&#x20;   logger.warning("startup\_orphaned\_files", count=len(orphans),

&#x20;                  paths=\[str(p) for p in orphans])

&#x20; 

&#x20; cleanup\_task = asyncio.create\_task(\_periodic\_job\_cleanup())

&#x20; 

&#x20; yield

&#x20; 

&#x20; # SHUTDOWN

&#x20; cleanup\_task.cancel()

&#x20; with suppress(asyncio.CancelledError):

&#x20;   await cleanup\_task



app = FastAPI(

&#x20; title="AuraScript API",

&#x20; description="High-accuracy Manglish transcription powered by Gemini AI",

&#x20; version="1.0.0",

&#x20; docs\_url="/docs" if not settings.is\_production else None,

&#x20; redoc\_url="/redoc" if not settings.is\_production else None,

&#x20; lifespan=lifespan

)



MIDDLEWARE (in order):

1\. TrustedHostMiddleware:

&#x20;    allowed\_hosts=\["www.aurascript.au", "www.aurascript.store", 

&#x20;                   "localhost", "127.0.0.1"]



2\. CORSMiddleware:

&#x20;    allow\_origins=settings.ALLOWED\_ORIGINS

&#x20;    allow\_credentials=True

&#x20;    allow\_methods=\["GET", "POST", "DELETE", "OPTIONS"]

&#x20;    allow\_headers=\["Content-Type", "X-API-Key", "X-Request-ID"]

&#x20;    expose\_headers=\["X-Request-ID", "X-Job-ID", "Retry-After"]

&#x20;    max\_age=600



3\. Request ID Middleware (custom):

&#x20;    Inject unique X-Request-ID on every request.

&#x20;    Bind request\_id to structlog context for that request.



EXCEPTION HANDLERS:

&#x20; RequestValidationError → 422 with field-level error messages

&#x20; AudioProcessingError   → 422 with safe message

&#x20; HTTPException          → pass through as-is

&#x20; Exception              → 500 with request\_id but NO internal details



Include routers: transcription, websocket, health



══════════════════════════════════════════════════════════════════════════

PHASE 7 — DEPLOYMENT

Files: Dockerfile, docker-compose.yml, docker-compose.prod.yml,

&#x20;      nginx/aurascript.conf, scripts/setup\_linode.sh, scripts/deploy.sh,

&#x20;      scripts/healthcheck.sh, .github/workflows/deploy.yml,

&#x20;      requirements.txt, requirements-dev.txt, README.md

══════════════════════════════════════════════════════════════════════════



── Dockerfile ──────────────────────────────────────────────────────────



FROM python:3.11-slim



\# Install system dependencies

RUN apt-get update \&\& apt-get install -y --no-install-recommends \\

&#x20;   ffmpeg \\

&#x20;   libmagic1 \\

&#x20;   curl \\

&#x20;   \&\& rm -rf /var/lib/apt/lists/\*



WORKDIR /app



\# Non-root user for security

RUN useradd -m -u 1000 -s /bin/bash aurascript



\# Install Python deps before copying code (layer cache optimization)

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt



\# Copy application

COPY --chown=aurascript:aurascript . .



\# Create temp directories with correct ownership

RUN mkdir -p /tmp/aurascript/uploads /tmp/aurascript/chunks \\

&#x20;   \&\& chown -R aurascript:aurascript /tmp/aurascript



USER aurascript



EXPOSE 8080



HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \\

&#x20; CMD curl -f http://localhost:8080/health || exit 1



CMD \["uvicorn", "main:app", \\

&#x20;    "--host", "0.0.0.0", \\

&#x20;    "--port", "8080", \\

&#x20;    "--workers", "1", \\

&#x20;    "--loop", "uvloop", \\

&#x20;    "--http", "httptools", \\

&#x20;    "--log-config", "logging.json"]



── nginx/aurascript.conf ───────────────────────────────────────────────



Generate complete Nginx config for:

&#x20; - Both domains: www.aurascript.au AND www.aurascript.store

&#x20; - www.aurascript.store → 301 redirect to www.aurascript.au

&#x20; - SSL termination (Certbot/Let's Encrypt paths)

&#x20; - WebSocket upgrade headers (critical for /ws/ paths)

&#x20; - Large file upload: client\_max\_body\_size 750M

&#x20; - Proxy to uvicorn on localhost:8080

&#x20; - Security headers:

&#x20;     Strict-Transport-Security: max-age=31536000; includeSubDomains

&#x20;     X-Frame-Options: DENY

&#x20;     X-Content-Type-Options: nosniff

&#x20;     Referrer-Policy: strict-origin-when-cross-origin

&#x20; - Gzip compression for JSON responses

&#x20; - Rate limiting at Nginx level (additional layer):

&#x20;     10 requests/second per IP on /transcribe

&#x20;     No limit on /health and /ws/ (WebSocket)



── scripts/setup\_linode.sh ─────────────────────────────────────────────



Complete Linode Ubuntu 22.04 setup script:

&#x20; - System update

&#x20; - Install: docker, docker-compose, nginx, certbot, git, ufw

&#x20; - UFW firewall: allow 22 (SSH), 80 (HTTP), 443 (HTTPS), deny all else

&#x20; - Certbot SSL for www.aurascript.au and www.aurascript.store

&#x20; - Clone GitHub repo

&#x20; - Copy .env.example → .env (with instructions to fill in)

&#x20; - Start Docker containers

&#x20; - Enable nginx

&#x20; - Print post-setup checklist



── .github/workflows/deploy.yml ────────────────────────────────────────



CI/CD pipeline:

&#x20; Trigger: push to main branch



&#x20; Jobs:

&#x20; 1. test:

&#x20;      Run pytest with coverage.

&#x20;      Fail pipeline if coverage < 80%.

&#x20;      

&#x20; 2. build:

&#x20;      Build Docker image.

&#x20;      Push to GitHub Container Registry (ghcr.io).

&#x20;      Tag with git SHA.

&#x20;      

&#x20; 3. deploy (only if test + build pass):

&#x20;      SSH to Linode using GitHub Secret LINODE\_SSH\_KEY.

&#x20;      Execute scripts/deploy.sh remotely.

&#x20;      Run scripts/healthcheck.sh to verify deployment.

&#x20;      Post deployment status to GitHub commit status.



── requirements.txt ────────────────────────────────────────────────────



fastapi==0.111.0

uvicorn\[standard]==0.29.0

uvloop==0.19.0

httptools==0.6.1

python-multipart==0.0.9

aiofiles==23.2.1

vertexai>=1.49.0

google-cloud-aiplatform>=1.49.0

google-api-core>=2.19.0

tenacity==8.3.0

pydantic-settings==2.3.0

python-magic==0.4.27

structlog==24.2.0

httpx==0.27.0

websockets==12.0



── requirements-dev.txt ────────────────────────────────────────────────



pytest==8.2.0

pytest-asyncio==0.23.7

pytest-cov==5.0.0

httpx==0.27.0

pytest-mock==3.14.0

black==24.4.2

ruff==0.4.7

mypy==1.10.0



══════════════════════════════════════════════════════════════════════════

PHASE 8 — FRONTEND INTEGRATION (BLOCKED — SEE INTEGRATION GATE)

══════════════════════════════════════════════════════════════════════════



This phase is LOCKED until the Integration Gate in Rule 3 is completed.



After the developer answers the Integration Gate questions, generate:



&#x20; FRONTEND\_INTEGRATION.md:

&#x20;   Complete integration guide tailored to the specific answers given.

&#x20;   Include actual URLs: www.aurascript.au

&#x20;   Include actual WebSocket URL format.

&#x20;   Include copy-paste JavaScript code for the chosen integration method.

&#x20;   Include webhook signature verification code.

&#x20;   Include CORS troubleshooting specific to Lovable.dev hosting.



&#x20; Integration code in new file: integration/lovable\_client\_spec.md

&#x20;   API sequence diagrams.

&#x20;   All event\_type strings the frontend must handle.

&#x20;   Error handling decision tree.

&#x20;   Reconnection logic pseudocode.



══════════════════════════════════════════════════════════════════════════

CROSS-CUTTING REQUIREMENTS (Apply to every file generated)

══════════════════════════════════════════════════════════════════════════



LOGGING — Use structlog throughout:

&#x20; Every log entry must include: timestamp, level, job\_id, request\_id,

&#x20; module, function name.

&#x20; NEVER log: audio bytes, API keys, file contents, full file paths in prod.

&#x20; Log levels:

&#x20;   DEBUG:   Chunk-level operations, event emissions

&#x20;   INFO:    Job state transitions, API requests

&#x20;   WARNING: Retries, cleanup failures, quality flags, orphaned files

&#x20;   ERROR:   Exceptions, Gemini failures, parse errors



TYPING — Strict throughout:

&#x20; Python 3.11+ syntax.

&#x20; No bare dict or list (use dict\[str, str], list\[Path]).

&#x20; Annotated constraints on all numeric fields.

&#x20; Return types on every function.



CODE QUALITY:

&#x20; PEP 8, Black-compatible, 88-char line limit.

&#x20; No unused imports (ruff enforced).

&#x20; No mutable default arguments.

&#x20; No bare except clauses (always except SpecificException).



COST CONTROLS (Gemini API):

&#x20; Single-chunk files skip Phase 2 stitching entirely.

&#x20; Quality agent AI check only runs if heuristic\_score < 0.7.

&#x20; MAX\_CONCURRENT\_GEMINI\_CALLS semaphore prevents runaway API usage.

&#x20; Per-day rate limit per API key prevents cost overruns.

&#x20; Log Gemini call count and estimated token usage per job.

&#x20; Add estimated\_cost\_usd to job metadata (rough estimate for monitoring).



══════════════════════════════════════════════════════════════════════════

README.md CONTENT

══════════════════════════════════════════════════════════════════════════



Generate README.md containing:



\# AuraScript — Manglish Transcription API



\## What it does

\[Brief product description]



\## Architecture diagram (ASCII)

\[Show agents, event flow, WebSocket path]



\## Quick Start (Local Development)

1\. Prerequisites: Docker, docker-compose, ffmpeg, Google Cloud account

2\. Clone repo

3\. cp .env.example .env → fill in values

4\. docker-compose up

5\. Test: curl http://localhost:8080/health



\## Deployment to Linode

1\. Provision Ubuntu 22.04 Linode

2\. Run setup\_linode.sh

3\. Configure DNS for aurascript.au and aurascript.store

4\. Run certbot

5\. Set GitHub Secrets for CI/CD



\## API Reference

\[Link to /docs when running locally]



\## Environment Variables

\[Table of all variables with descriptions]



\## Frontend Integration

\[Link to FRONTEND\_INTEGRATION.md]

\[Note: Complete Integration Gate first]



══════════════════════════════════════════════════════════════════════════

BEGIN EXECUTION

══════════════════════════════════════════════════════════════════════════



Start with Phase 1.

Generate config.py first.

Follow all Agent Behaviour Rules exactly.

Do not proceed past Phase 7 without the Integration Gate responses.

