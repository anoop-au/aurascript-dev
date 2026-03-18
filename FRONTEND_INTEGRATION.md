# AuraScript × EchoScribe — Frontend Integration Guide

**Backend:** `https://www.aurascript.au`
**Frontend:** `https://echo-scribe-02.lovable.app`
**Schema version:** `1.1`
**Last updated:** 2026-03-18

---

## Overview

EchoScribe sends audio files to AuraScript via a direct browser upload, tracks
real-time transcription progress over WebSocket, and presents the completed
transcript with inline display, clipboard copy, and download options
(TXT / DOCX / PDF / JSON).

```
UploadZone ──POST /transcribe──► AuraScript backend
               ◄── 202 { job_id, websocket_url } ──────────────────────────┐
ProcessingScreen ──WS /ws/transcribe/{job_id}──────────────────────────────┘
               ◄── stream of events (chunk progress, quality, heartbeat) ──┐
ResultsScreen ──GET /transcribe/result/{job_id}────────────────────────────┘
               ◄── { transcript, speaker_map, metadata }
```

---

## 1. Authentication

Every HTTP request and every WebSocket connection **must** include the API key.

| Transport | Method |
|-----------|--------|
| HTTP | `X-Api-Key: <key>` request header |
| WebSocket | `?token=<key>` query parameter on the WS URL |

```ts
// src/lib/api.ts
const API_KEY = import.meta.env.VITE_API_KEY;
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "https://www.aurascript.au";

export const apiHeaders = (): HeadersInit => ({
  "X-Api-Key": API_KEY,
});
```

> **Important:** `VITE_API_KEY` is injected at build time. Never expose it in
> client-visible source or logs.

---

## 2. Environment Variables

Create `.env.local` in your Lovable / Vite project root:

```bash
VITE_API_KEY=your-aurascript-api-key
VITE_API_BASE_URL=https://www.aurascript.au
```

For the Lovable hosted environment, set these in **Project → Settings → Environment Variables**.

---

## 3. File Upload Constraints

| Constraint | Value | Notes |
|-----------|-------|-------|
| Max file size | **700 MB** | Backend hard limit — enforce client-side first |
| Accepted formats | MP3, WAV, M4A, OGG, FLAC, AAC, WEBM | Validate by extension + MIME type |
| Content-Type | `multipart/form-data` | Required for `UploadFile` parsing |
| Max duration | 2 hours | Enforced by backend after audio analysis |

> The user-facing limit is 700 MB (backend enforces 700 MB via HTTP 413).
> Although your users may have files up to 800 MB, anything above 700 MB will
> be rejected with a `413 Content Too Large` response. Show a friendly error:
> *"File exceeds 700 MB limit — please compress or split the audio."*

---

## 4. UploadZone — `POST /transcribe`

### Request
```ts
// src/components/UploadZone.tsx (fetch call)
async function submitTranscription(
  file: File,
  options: { languageHint?: string; numSpeakers?: number; webhookUrl?: string }
): Promise<TranscribeResponse> {
  // Client-side guard
  if (file.size > 700 * 1024 * 1024) {
    throw new Error("FILE_TOO_LARGE");
  }

  const form = new FormData();
  form.append("file", file);
  if (options.languageHint) form.append("language_hint", options.languageHint);
  if (options.numSpeakers)  form.append("num_speakers", String(options.numSpeakers));
  if (options.webhookUrl)   form.append("webhook_url", options.webhookUrl);

  const res = await fetch(`${BASE_URL}/transcribe`, {
    method: "POST",
    headers: apiHeaders(),  // DO NOT set Content-Type — browser sets boundary
    body: form,
  });

  if (!res.ok) await handleHttpError(res);
  return res.json() as Promise<TranscribeResponse>;
}
```

### Response `202 Accepted`
```ts
interface TranscribeResponse {
  job_id: string;          // UUID — store this for status polling and WS
  status: "pending";
  websocket_url: string;   // wss://www.aurascript.au/ws/transcribe/{job_id}
  poll_url: string;        // https://www.aurascript.au/transcribe/status/{job_id}
  result_url: string;      // https://www.aurascript.au/transcribe/result/{job_id}
  message: string;
}
```

After receiving 202, immediately navigate to `ProcessingScreen` and open the WebSocket.

---

## 5. ProcessingScreen — WebSocket Event Stream

### Connecting
```ts
// src/components/ProcessingScreen.tsx
function openTranscriptionSocket(
  jobId: string,
  lastSequence: number = 0
): WebSocket {
  const url = new URL(`${BASE_URL.replace("https", "wss")}/ws/transcribe/${jobId}`);
  url.searchParams.set("token", API_KEY);
  if (lastSequence > 0) url.searchParams.set("last_sequence", String(lastSequence));

  return new WebSocket(url.toString());
}
```

### Event Schema (all events)
```ts
interface BaseEvent {
  event_type: string;
  job_id: string;
  timestamp: string;   // ISO 8601 UTC
  sequence: number;    // monotonically increasing per job
  schema_version: "1.1";
}
```

### Events Reference

| `event_type` | Stage | Key Fields | UI Action |
|---|---|---|---|
| `job.accepted` | 0 | `message` | Show spinner |
| `job.audio_analyzed` | 1 | `duration_seconds`, `channels`, `sample_rate`, `quality_warnings[]` | Show duration |
| `job.plan_created` | 2 | `chunk_count`, `strategy` | Show "N chunks planned" |
| `job.chunking_started` | 3 | — | Progress: segmenting |
| `job.chunking_complete` | 3 | `chunk_count` | Progress: chunks ready |
| `job.chunk_processing_started` | 4 | `chunk_index`, `total_chunks` | Highlight chunk in timeline |
| `job.chunk_transcribed` | 4 | `chunk_index`, `preview`, `confidence_score` | Append preview text |
| `job.quality_checked` | 5 | `chunk_index`, `score`, `decision` (`accept`/`retry`/`flag`), `issues[]` | Show quality badge |
| `job.chunk_retry` | 6 | `chunk_index`, `reason` | Show retry indicator |
| `job.stitching_started` | 8 | — | Show "Finalising…" |
| `job.stitching_complete` | 8 | — | Show "Almost done…" |
| `job.complete` | 9 | `transcript`, `speaker_map`, `metadata` | Navigate → ResultsScreen |
| `job.failed` | — | `error_code`, `error_message` | Show error state |
| `job.progress_heartbeat` | 4 | `progress_pct`, `chunks_done`, `total_chunks` | Update progress bar |
| `job.agent_decision` | any | `agent`, `decision`, `reason` | (debug panel only) |

### Recommended Progress Calculation
```ts
function calcProgress(event: AnyEvent, state: ProcessingState): number {
  switch (event.event_type) {
    case "job.accepted":            return 2;
    case "job.audio_analyzed":      return 5;
    case "job.plan_created":        return 8;
    case "job.chunking_complete":   return 12;
    case "job.progress_heartbeat":  return 12 + (event.progress_pct * 0.75);
    case "job.stitching_started":   return 90;
    case "job.stitching_complete":  return 97;
    case "job.complete":            return 100;
    default:                        return state.progress;
  }
}
```

### Reconnection Logic
```ts
class TranscriptionSocket {
  private ws: WebSocket | null = null;
  private lastSequence = 0;
  private reconnectAttempts = 0;

  connect(jobId: string) {
    this.ws = openTranscriptionSocket(jobId, this.lastSequence);

    this.ws.onmessage = (e) => {
      const event: AnyEvent = JSON.parse(e.data);
      this.lastSequence = event.sequence;
      this.handleEvent(event);
    };

    this.ws.onclose = (e) => {
      if (e.code === 1000) return; // clean close (job done)
      if (this.reconnectAttempts < 5) {
        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000);
        this.reconnectAttempts++;
        setTimeout(() => this.connect(jobId), delay);
      }
    };
  }

  disconnect() { this.ws?.close(1000); }
}
```

> **Missed events:** On reconnect, pass `last_sequence=N` and the server
> replays all events after sequence N (up to last 100 events per job).

### Fallback Polling (if WebSocket unavailable)
```ts
async function pollUntilComplete(
  jobId: string,
  onUpdate: (s: JobStatusResponse) => void
): Promise<JobResultResponse> {
  while (true) {
    const res = await fetch(`${BASE_URL}/transcribe/status/${jobId}`, {
      headers: apiHeaders(),
    });
    const status: JobStatusResponse = await res.json();
    onUpdate(status);

    if (status.status === "completed") {
      return fetch(`${BASE_URL}/transcribe/result/${jobId}`, {
        headers: apiHeaders(),
      }).then(r => r.json());
    }
    if (status.status === "failed") throw new Error(status.error_code ?? "FAILED");
    if (status.status === "cancelled") throw new Error("CANCELLED");

    await new Promise(r => setTimeout(r, 3000));
  }
}
```

---

## 6. ResultsScreen — Fetching and Displaying Results

The `job.complete` WebSocket event includes the full transcript inline. You can
use it directly **or** fetch from `result_url` (identical payload):

```ts
interface JobResultResponse {
  job_id: string;
  status: "completed";
  transcript: string;       // Full timestamped transcript
  speaker_map: Record<string, string>; // { "Speaker 1": "Speaker 1", ... }
  metadata: {
    duration_seconds: number;
    chunk_count: number;
    processing_time_seconds?: number;
    [key: string]: unknown;
  };
}
```

### Transcript Format
```
[00:00] Speaker 1: Okay so let me explain lah, the problem is quite simple one.
[00:08] Speaker 2: Ya kan, I also think so. We should just do it this way lor.
[00:15] Speaker 1: But the budget mah, how?
[01:32] Speaker 1: [inaudible] then we proceed.
```

- Timestamps: `[MM:SS]` (< 1 hour) or `[HH:MM:SS]` (≥ 1 hour)
- Inaudible segments: `[inaudible]`
- Background sounds: `[background noise]`, `[laughter]`, etc.

---

## 7. Downloads (ResultsScreen)

All downloads are generated client-side from the `transcript` string.

### TXT
```ts
function downloadTxt(transcript: string, filename: string) {
  const blob = new Blob([transcript], { type: "text/plain;charset=utf-8" });
  triggerDownload(blob, `${filename}.txt`);
}
```

### JSON
```ts
function downloadJson(result: JobResultResponse, filename: string) {
  const blob = new Blob(
    [JSON.stringify(result, null, 2)],
    { type: "application/json" }
  );
  triggerDownload(blob, `${filename}.json`);
}
```

### DOCX
Use [`docx`](https://www.npmjs.com/package/docx) (browser-compatible):
```ts
import { Document, Paragraph, TextRun, Packer } from "docx";

async function downloadDocx(transcript: string, filename: string) {
  const lines = transcript.split("\n").filter(Boolean);
  const doc = new Document({
    sections: [{
      properties: {},
      children: lines.map(line => new Paragraph({
        children: [new TextRun({ text: line, font: "Calibri", size: 24 })],
        spacing: { after: 120 },
      })),
    }],
  });
  const blob = await Packer.toBlob(doc);
  triggerDownload(blob, `${filename}.docx`);
}
```

### PDF
Use [`jspdf`](https://www.npmjs.com/package/jspdf):
```ts
import jsPDF from "jspdf";

function downloadPdf(transcript: string, metadata: JobResultResponse["metadata"], filename: string) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const lines = doc.splitTextToSize(transcript, 170);
  doc.setFont("helvetica").setFontSize(10);
  let y = 20;
  for (const line of lines) {
    if (y > 280) { doc.addPage(); y = 20; }
    doc.text(line, 20, y);
    y += 6;
  }
  doc.save(`${filename}.pdf`);
}
```

### Trigger helper
```ts
function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
```

---

## 8. Error Handling

### HTTP Error Codes

| Status | Meaning | UI Message |
|--------|---------|------------|
| `401` | Invalid/missing API key | "Authentication failed. Contact support." |
| `413` | File exceeds 700 MB | "File too large. Max size is 700 MB." |
| `422` | Invalid file type or form field | Show `detail[].msg` from response body |
| `429` | Rate limit hit | `Retry-After` header tells you when to retry |
| `503` | Server at capacity | "Service busy. Please try again in 30 seconds." |
| `500` | Internal error | "Something went wrong. Job ID: {job_id}" |

```ts
async function handleHttpError(res: Response): Promise<never> {
  const body = await res.json().catch(() => ({}));
  throw Object.assign(new Error(body.message ?? res.statusText), {
    status: res.status,
    code: body.error_code,
    retryAfter: res.headers.get("Retry-After"),
    requestId: res.headers.get("X-Request-ID"),
    detail: body.detail,
  });
}
```

### WebSocket Close Codes

| Code | Meaning |
|------|---------|
| `1000` | Normal close (job done or cancelled) |
| `1008` | Authentication failed — do not reconnect |
| `1001` | Server going away — reconnect with backoff |

### Job Failed Event
```ts
interface JobFailedEvent extends BaseEvent {
  event_type: "job.failed";
  error_code: "INVALID_AUDIO" | "TRANSCRIPTION_FAILED" | "STORAGE_ERROR" | "INTERNAL_ERROR";
  error_message: string;
}
```

| `error_code` | User-Facing Message |
|---|---|
| `INVALID_AUDIO` | "This file couldn't be processed. Please check the audio format." |
| `TRANSCRIPTION_FAILED` | "Transcription failed. Please try again." |
| `STORAGE_ERROR` | "Upload failed due to a storage error. Please try again." |
| `INTERNAL_ERROR` | "An unexpected error occurred. Job ID: {job_id}" |

---

## 9. Job Cancellation

```ts
async function cancelJob(jobId: string): Promise<void> {
  await fetch(`${BASE_URL}/transcribe/${jobId}`, {
    method: "DELETE",
    headers: apiHeaders(),
  });
}
```

Call this when the user navigates away from `ProcessingScreen` mid-job.
Also close the WebSocket (`ws.close(1000)`) on cleanup.

---

## 10. TypeScript Types (copy into `src/types/aurascript.ts`)

See [`integration/lovable_client_spec.md`](integration/lovable_client_spec.md)
for the complete typed client, all event interfaces, and React hook implementations.
