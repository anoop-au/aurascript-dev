# AuraScript — Lovable Client Specification

**Target app:** `https://echo-scribe-02.lovable.app`
**Backend:** `https://www.aurascript.au`
**Schema version:** `1.1`

This document is the single source of truth for how EchoScribe's Lovable
frontend communicates with the AuraScript backend. Copy/paste each section
directly into your Lovable project.

---

## File: `src/types/aurascript.ts`

```ts
// ── Base event ────────────────────────────────────────────────────────────────
export interface BaseEvent {
  event_type: string;
  job_id: string;
  timestamp: string;
  sequence: number;
  schema_version: "1.1";
}

// ── All 15 event types ────────────────────────────────────────────────────────
export interface JobAcceptedEvent extends BaseEvent {
  event_type: "job.accepted";
  message: string;
}

export interface AudioAnalyzedEvent extends BaseEvent {
  event_type: "job.audio_analyzed";
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  codec: string;
  bitrate: number;
  quality_warnings: string[];
}

export interface PlanCreatedEvent extends BaseEvent {
  event_type: "job.plan_created";
  chunk_count: number;
  strategy: string;
  estimated_duration_seconds: number;
}

export interface ChunkingStartedEvent extends BaseEvent {
  event_type: "job.chunking_started";
}

export interface ChunkingCompleteEvent extends BaseEvent {
  event_type: "job.chunking_complete";
  chunk_count: number;
}

export interface ChunkProcessingStartedEvent extends BaseEvent {
  event_type: "job.chunk_processing_started";
  chunk_index: number;
  total_chunks: number;
}

export interface ChunkTranscribedEvent extends BaseEvent {
  event_type: "job.chunk_transcribed";
  chunk_index: number;
  preview: string;          // first 200 chars of chunk transcript
  confidence_score: number; // 0.0–1.0
}

export interface QualityCheckedEvent extends BaseEvent {
  event_type: "job.quality_checked";
  chunk_index: number;
  score: number;
  decision: "accept" | "retry" | "flag";
  issues: string[];
}

export interface ChunkRetryEvent extends BaseEvent {
  event_type: "job.chunk_retry";
  chunk_index: number;
  reason: string;
}

export interface StitchingStartedEvent extends BaseEvent {
  event_type: "job.stitching_started";
}

export interface StitchingCompleteEvent extends BaseEvent {
  event_type: "job.stitching_complete";
}

export interface JobCompleteEvent extends BaseEvent {
  event_type: "job.complete";
  transcript: string;
  speaker_map: Record<string, string>;
  metadata: TranscriptMetadata;
}

export interface JobFailedEvent extends BaseEvent {
  event_type: "job.failed";
  error_code: "INVALID_AUDIO" | "TRANSCRIPTION_FAILED" | "STORAGE_ERROR" | "INTERNAL_ERROR";
  error_message: string;
}

export interface AgentDecisionEvent extends BaseEvent {
  event_type: "job.agent_decision";
  agent: string;
  decision: string;
  reason: string;
}

export interface ProgressHeartbeatEvent extends BaseEvent {
  event_type: "job.progress_heartbeat";
  progress_pct: number;
  chunks_done: number;
  total_chunks: number;
}

export type AnyEvent =
  | JobAcceptedEvent
  | AudioAnalyzedEvent
  | PlanCreatedEvent
  | ChunkingStartedEvent
  | ChunkingCompleteEvent
  | ChunkProcessingStartedEvent
  | ChunkTranscribedEvent
  | QualityCheckedEvent
  | ChunkRetryEvent
  | StitchingStartedEvent
  | StitchingCompleteEvent
  | JobCompleteEvent
  | JobFailedEvent
  | AgentDecisionEvent
  | ProgressHeartbeatEvent;

// ── HTTP response types ───────────────────────────────────────────────────────
export interface TranscribeResponse {
  job_id: string;
  status: "pending";
  websocket_url: string;
  poll_url: string;
  result_url: string;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed" | "cancelled";
  progress_pct: number;
  error_code?: string;
  error_message?: string;
  created_at: string;
  updated_at: string;
}

export interface TranscriptMetadata {
  duration_seconds: number;
  chunk_count: number;
  processing_time_seconds?: number;
  [key: string]: unknown;
}

export interface JobResultResponse {
  job_id: string;
  status: "completed";
  transcript: string;
  speaker_map: Record<string, string>;
  metadata: TranscriptMetadata;
}

export interface ApiError {
  status: number;
  code?: string;
  message: string;
  retryAfter?: string | null;
  requestId?: string | null;
  detail?: Array<{ loc: string[]; msg: string; type: string }>;
}

// ── Upload options ────────────────────────────────────────────────────────────
export interface TranscribeOptions {
  languageHint?: string;
  numSpeakers?: number;
  webhookUrl?: string;
}

// ── Processing state for ProcessingScreen ────────────────────────────────────
export interface ProcessingState {
  progress: number;
  stage: string;
  chunkCount: number;
  chunksComplete: number;
  previewLines: string[];   // growing transcript preview
  qualityScores: number[];  // per-chunk scores
  audioInfo?: {
    durationSeconds: number;
    qualityWarnings: string[];
  };
}
```

---

## File: `src/lib/api.ts`

```ts
import type {
  TranscribeResponse,
  TranscribeOptions,
  JobStatusResponse,
  JobResultResponse,
  ApiError,
} from "@/types/aurascript";

const API_KEY  = import.meta.env.VITE_API_KEY as string;
const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "https://www.aurascript.au";

// Max enforced by backend — show friendly error above this
export const MAX_FILE_BYTES = 700 * 1024 * 1024;

export const ACCEPTED_MIME_TYPES = [
  "audio/mpeg", "audio/mp3",
  "audio/wav", "audio/x-wav",
  "audio/mp4", "audio/m4a", "audio/x-m4a",
  "audio/ogg",
  "audio/flac", "audio/x-flac",
  "audio/aac",
  "audio/webm", "video/webm",
];

export const ACCEPTED_EXTENSIONS = ".mp3,.wav,.m4a,.ogg,.flac,.aac,.webm";

// ── Headers ───────────────────────────────────────────────────────────────────
function authHeaders(): HeadersInit {
  return { "X-Api-Key": API_KEY };
}

// ── Error helper ──────────────────────────────────────────────────────────────
async function parseError(res: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try { body = await res.json(); } catch { /* non-JSON body */ }
  return {
    status: res.status,
    code: body.error_code as string | undefined,
    message: (body.message as string | undefined) ?? res.statusText,
    retryAfter: res.headers.get("Retry-After"),
    requestId: res.headers.get("X-Request-ID"),
    detail: body.detail as ApiError["detail"],
  };
}

// ── POST /transcribe ──────────────────────────────────────────────────────────
export async function submitTranscription(
  file: File,
  options: TranscribeOptions = {}
): Promise<TranscribeResponse> {
  if (file.size > MAX_FILE_BYTES) {
    throw { status: 413, message: "File exceeds 700 MB limit.", code: "FILE_TOO_LARGE" } as ApiError;
  }

  const form = new FormData();
  form.append("file", file);
  if (options.languageHint)  form.append("language_hint", options.languageHint);
  if (options.numSpeakers)   form.append("num_speakers", String(options.numSpeakers));
  if (options.webhookUrl)    form.append("webhook_url", options.webhookUrl);

  // Do NOT set Content-Type — browser must set multipart boundary
  const res = await fetch(`${BASE_URL}/transcribe`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!res.ok) throw await parseError(res);
  return res.json();
}

// ── GET /transcribe/status/{job_id} ──────────────────────────────────────────
export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${BASE_URL}/transcribe/status/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// ── GET /transcribe/result/{job_id} ──────────────────────────────────────────
export async function getJobResult(jobId: string): Promise<JobResultResponse> {
  const res = await fetch(`${BASE_URL}/transcribe/result/${jobId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw await parseError(res);
  return res.json();
}

// ── DELETE /transcribe/{job_id} ───────────────────────────────────────────────
export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`${BASE_URL}/transcribe/${jobId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

// ── WebSocket URL builder ─────────────────────────────────────────────────────
export function buildWsUrl(jobId: string, lastSequence: number = 0): string {
  const wsBase = BASE_URL.replace(/^https/, "wss").replace(/^http/, "ws");
  const url = new URL(`${wsBase}/ws/transcribe/${jobId}`);
  url.searchParams.set("token", API_KEY);
  if (lastSequence > 0) url.searchParams.set("last_sequence", String(lastSequence));
  return url.toString();
}

// ── Fallback polling ──────────────────────────────────────────────────────────
export async function pollUntilComplete(
  jobId: string,
  onUpdate: (s: JobStatusResponse) => void,
  intervalMs = 3000
): Promise<JobResultResponse> {
  while (true) {
    const status = await getJobStatus(jobId);
    onUpdate(status);
    if (status.status === "completed") return getJobResult(jobId);
    if (status.status === "failed")    throw { status: 500, message: status.error_message ?? "Job failed", code: status.error_code } as ApiError;
    if (status.status === "cancelled") throw { status: 400, message: "Job cancelled", code: "CANCELLED" } as ApiError;
    await new Promise(r => setTimeout(r, intervalMs));
  }
}
```

---

## File: `src/hooks/useTranscriptionSocket.ts`

```ts
import { useEffect, useRef, useCallback, useState } from "react";
import { buildWsUrl } from "@/lib/api";
import type { AnyEvent, ProcessingState, JobCompleteEvent, JobFailedEvent } from "@/types/aurascript";

export type SocketStatus = "connecting" | "connected" | "reconnecting" | "closed" | "failed";

interface UseTranscriptionSocketOptions {
  jobId: string | null;
  onComplete: (event: JobCompleteEvent) => void;
  onFailed:   (event: JobFailedEvent) => void;
}

export function useTranscriptionSocket({
  jobId,
  onComplete,
  onFailed,
}: UseTranscriptionSocketOptions) {
  const [state, setState] = useState<ProcessingState>({
    progress: 0,
    stage: "Waiting…",
    chunkCount: 0,
    chunksComplete: 0,
    previewLines: [],
    qualityScores: [],
  });
  const [socketStatus, setSocketStatus] = useState<SocketStatus>("connecting");

  const wsRef              = useRef<WebSocket | null>(null);
  const lastSequenceRef    = useRef(0);
  const reconnectAttemptsRef = useRef(0);
  const isMountedRef       = useRef(true);

  const connect = useCallback(() => {
    if (!jobId || !isMountedRef.current) return;

    setSocketStatus(reconnectAttemptsRef.current > 0 ? "reconnecting" : "connecting");
    const ws = new WebSocket(buildWsUrl(jobId, lastSequenceRef.current));
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      reconnectAttemptsRef.current = 0;
      setSocketStatus("connected");
    };

    ws.onmessage = (e: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const event: AnyEvent = JSON.parse(e.data as string);
        lastSequenceRef.current = event.sequence;
        handleEvent(event);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = (e: CloseEvent) => {
      if (!isMountedRef.current) return;
      if (e.code === 1000) { setSocketStatus("closed"); return; }
      if (e.code === 1008) { setSocketStatus("failed"); return; } // auth failure — don't retry
      if (reconnectAttemptsRef.current < 5) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptsRef.current, 30_000);
        reconnectAttemptsRef.current++;
        setTimeout(connect, delay);
      } else {
        setSocketStatus("failed");
      }
    };

    ws.onerror = () => { ws.close(); };
  }, [jobId]);

  function handleEvent(event: AnyEvent) {
    setState(prev => {
      switch (event.event_type) {
        case "job.accepted":
          return { ...prev, progress: 2, stage: "Job accepted…" };

        case "job.audio_analyzed":
          return {
            ...prev,
            progress: 5,
            stage: `Audio analysed — ${Math.round(event.duration_seconds)}s`,
            audioInfo: {
              durationSeconds: event.duration_seconds,
              qualityWarnings: event.quality_warnings,
            },
          };

        case "job.plan_created":
          return {
            ...prev,
            progress: 8,
            stage: `Planning ${event.chunk_count} chunks…`,
            chunkCount: event.chunk_count,
          };

        case "job.chunking_complete":
          return { ...prev, progress: 12, stage: "Audio segmented.", chunkCount: event.chunk_count };

        case "job.chunk_transcribed":
          return {
            ...prev,
            chunksComplete: prev.chunksComplete + 1,
            previewLines: [...prev.previewLines, event.preview],
          };

        case "job.quality_checked": {
          const scores = [...prev.qualityScores];
          scores[event.chunk_index] = event.score;
          return { ...prev, qualityScores: scores };
        }

        case "job.progress_heartbeat":
          return {
            ...prev,
            progress: Math.max(prev.progress, 12 + event.progress_pct * 0.75),
            stage: `Transcribing… ${event.chunks_done}/${event.total_chunks} chunks`,
            chunksComplete: event.chunks_done,
          };

        case "job.stitching_started":
          return { ...prev, progress: 90, stage: "Stitching transcript…" };

        case "job.stitching_complete":
          return { ...prev, progress: 97, stage: "Finalising…" };

        case "job.complete":
          onComplete(event);
          return { ...prev, progress: 100, stage: "Complete!" };

        case "job.failed":
          onFailed(event);
          return { ...prev, stage: "Failed." };

        default:
          return prev;
      }
    });
  }

  useEffect(() => {
    isMountedRef.current = true;
    connect();
    return () => {
      isMountedRef.current = false;
      wsRef.current?.close(1000);
    };
  }, [connect]);

  const cancel = useCallback(() => {
    wsRef.current?.close(1000);
  }, []);

  return { state, socketStatus, cancel };
}
```

---

## File: `src/hooks/useDownloads.ts`

```ts
import type { JobResultResponse } from "@/types/aurascript";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement("a");
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function safeFilename(jobId: string): string {
  return `aurascript_${jobId.slice(0, 8)}`;
}

export function useDownloads(result: JobResultResponse | null) {
  const filename = result ? safeFilename(result.job_id) : "transcript";

  async function downloadTxt() {
    if (!result) return;
    triggerDownload(
      new Blob([result.transcript], { type: "text/plain;charset=utf-8" }),
      `${filename}.txt`
    );
  }

  async function downloadJson() {
    if (!result) return;
    triggerDownload(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
      `${filename}.json`
    );
  }

  async function downloadDocx() {
    if (!result) return;
    // Requires: npm install docx
    const { Document, Paragraph, TextRun, Packer } = await import("docx");
    const lines = result.transcript.split("\n").filter(Boolean);
    const doc = new Document({
      sections: [{
        properties: {},
        children: lines.map(line =>
          new Paragraph({
            children: [new TextRun({ text: line, font: "Calibri", size: 24 })],
            spacing: { after: 120 },
          })
        ),
      }],
    });
    triggerDownload(await Packer.toBlob(doc), `${filename}.docx`);
  }

  async function downloadPdf() {
    if (!result) return;
    // Requires: npm install jspdf
    const { default: jsPDF } = await import("jspdf");
    const doc   = new jsPDF({ unit: "mm", format: "a4" });
    const lines = doc.splitTextToSize(result.transcript, 170) as string[];
    doc.setFont("helvetica").setFontSize(10);
    let y = 20;
    for (const line of lines) {
      if (y > 280) { doc.addPage(); y = 20; }
      doc.text(line, 20, y);
      y += 6;
    }
    doc.save(`${filename}.pdf`);
  }

  function copyToClipboard(): Promise<void> {
    if (!result) return Promise.resolve();
    return navigator.clipboard.writeText(result.transcript);
  }

  return { downloadTxt, downloadJson, downloadDocx, downloadPdf, copyToClipboard };
}
```

---

## Component Integration Summary

### UploadZone
```
State:  idle → validating → uploading → submitted
Error:  FILE_TOO_LARGE | INVALID_TYPE | API_ERROR
Action: call submitTranscription(file, options)
        on success → navigate to ProcessingScreen with job_id
```

### ProcessingScreen
```
State:  connecting → live → reconnecting → complete | failed
Hook:   useTranscriptionSocket({ jobId, onComplete, onFailed })
Props:  job_id (from router state or URL param)
Action: onComplete → store result, navigate to ResultsScreen
        onFailed   → show error with error_code mapped to message
        unmount    → cancelJob(jobId) if status is not complete/failed
```

### ResultsScreen
```
State:  displaying result
Data:   JobCompleteEvent payload OR GET /transcribe/result/{job_id}
Hook:   useDownloads(result)
Action: copy → copyToClipboard()
        download buttons → downloadTxt | downloadDocx | downloadPdf | downloadJson
        new job → navigate to UploadZone
```

---

## Environment Setup

```bash
# .env.local (Vite project root)
VITE_API_KEY=your-aurascript-api-key-here
VITE_API_BASE_URL=https://www.aurascript.au
```

```bash
# Install client-side download libraries
npm install docx jspdf
```

---

## CORS Configuration

The backend allows these origins (already configured in `.env`):
```
https://echo-scribe-02.lovable.app
http://localhost:5173
```

If you add a custom domain to your Lovable app, update `ALLOWED_ORIGINS` in
`/opt/aurascript/aurascript/.env` and restart containers.

---

## Security Checklist

- [ ] `VITE_API_KEY` set in Lovable project environment variables (not committed to git)
- [ ] Client-side file size check (700 MB) before upload to save bandwidth
- [ ] Client-side MIME type check using `ACCEPTED_MIME_TYPES` list
- [ ] WebSocket reconnect stops on code `1008` (auth failure — don't retry)
- [ ] Job cancelled via `DELETE /transcribe/{job_id}` on component unmount
- [ ] Error messages shown to user never include stack traces or internal paths
- [ ] Webhook signatures verified server-side if using `webhook_url`
