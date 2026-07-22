"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/Header";
import * as api from "@/lib/api";
import { getApiErrorDetail, isApiErrorStatus } from "@/lib/errors";
import { loadGoalProfile } from "@/lib/goalProfile";
import { ALLOWED_UPLOAD_MIME_TYPES } from "@contracts/index";

// Mirrors services/api/app/config.py `max_upload_bytes` so obviously-oversized
// files are rejected before a network round trip.
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const MAX_FILES = 5;
const RETENTION_HOURS = 24;

const MIME_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "image/png": "PNG",
  "image/jpeg": "JPEG",
  "image/webp": "WEBP",
};

type UploadStatus = "pending" | "uploading" | "validated" | "rejected";

interface UploadFileState {
  clientId: string;
  file: File;
  status: UploadStatus;
  rejectionReason?: string;
  uploadId?: string;
  validatedAt?: number;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatRemaining(validatedAt: number, now: number): string {
  const deadline = validatedAt + RETENTION_HOURS * 60 * 60 * 1000;
  const remainingMs = deadline - now;
  if (remainingMs <= 0) return "deletion pending";
  const hours = Math.floor(remainingMs / (60 * 60 * 1000));
  const minutes = Math.floor((remainingMs % (60 * 60 * 1000)) / (60 * 1000));
  return `~${hours}h ${minutes}m`;
}

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<UploadFileState[]>([]);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [missingGoalProfile, setMissingGoalProfile] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [quotaExceeded, setQuotaExceeded] = useState<string | null>(null);

  useEffect(() => {
    setMissingGoalProfile(loadGoalProfile() === null);
  }, []);

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  function updateFile(clientId: string, patch: Partial<UploadFileState>) {
    setFiles((prev) => prev.map((f) => (f.clientId === clientId ? { ...f, ...patch } : f)));
  }

  async function uploadOne(entry: UploadFileState) {
    updateFile(entry.clientId, { status: "uploading" });
    try {
      const created = await api.createUpload({
        filename: entry.file.name,
        mime_type: entry.file.type,
        byte_size: entry.file.size,
      });
      await api.putUploadBytes(created.upload_url, entry.file);
      updateFile(entry.clientId, {
        status: "validated",
        uploadId: created.upload_id,
        validatedAt: Date.now(),
      });
    } catch (err) {
      updateFile(entry.clientId, {
        status: "rejected",
        rejectionReason: getApiErrorDetail(err),
      });
    }
  }

  function addFiles(fileList: FileList | File[]) {
    const incoming = Array.from(fileList);
    const activeCount = files.filter((f) => f.status !== "rejected").length;
    let slotsLeft = MAX_FILES - activeCount;

    const next: UploadFileState[] = [];
    for (const file of incoming) {
      const clientId = crypto.randomUUID();
      if (slotsLeft <= 0) {
        next.push({
          clientId,
          file,
          status: "rejected",
          rejectionReason: `Only ${MAX_FILES} files are allowed per analysis.`,
        });
        continue;
      }
      if (!ALLOWED_UPLOAD_MIME_TYPES.includes(file.type as (typeof ALLOWED_UPLOAD_MIME_TYPES)[number])) {
        next.push({
          clientId,
          file,
          status: "rejected",
          rejectionReason: `Unsupported file type${file.type ? ` (${file.type})` : ""}. Use PDF, PNG, JPEG, or WEBP.`,
        });
        continue;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        next.push({
          clientId,
          file,
          status: "rejected",
          rejectionReason: `File exceeds the ${MAX_UPLOAD_BYTES / (1024 * 1024)}MB limit.`,
        });
        continue;
      }
      next.push({ clientId, file, status: "pending" });
      slotsLeft -= 1;
    }

    setFiles((prev) => [...prev, ...next]);
    for (const entry of next) {
      if (entry.status === "pending") void uploadOne(entry);
    }
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDraggingOver(false);
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
  }

  function removeFile(clientId: string) {
    setFiles((prev) => prev.filter((f) => f.clientId !== clientId));
  }

  const validatedFiles = files.filter((f) => f.status === "validated");
  const canContinue = validatedFiles.length > 0 && !creating;

  async function handleContinue() {
    const goalProfile = loadGoalProfile();
    if (!goalProfile) {
      setMissingGoalProfile(true);
      return;
    }
    setCreating(true);
    setCreateError(null);
    setQuotaExceeded(null);
    try {
      const idempotencyKey = crypto.randomUUID();
      const result = await api.createAnalysis(
        { goal_profile: goalProfile, upload_ids: validatedFiles.map((f) => f.uploadId!) },
        idempotencyKey
      );
      router.push(`/analyses/${result.analysis_id}/processing`);
    } catch (err) {
      if (isApiErrorStatus(err, 429)) {
        setQuotaExceeded(getApiErrorDetail(err));
      } else {
        setCreateError(getApiErrorDetail(err));
      }
      setCreating(false);
    }
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="font-serif text-2xl text-ink">Upload your résumé or LinkedIn export</h1>
        <p className="mt-2 text-sm text-ink/70">
          Supported formats: {ALLOWED_UPLOAD_MIME_TYPES.map((m) => MIME_LABELS[m] ?? m).join(", ")}.
          Up to {MAX_FILES} files, {MAX_UPLOAD_BYTES / (1024 * 1024)}MB each.
        </p>

        <div className="mt-3 border-l-2 border-teal/60 pl-4">
          <p className="text-sm text-ink/70">
            Raw files are automatically deleted {RETENTION_HOURS} hours after upload. We keep the
            extracted analysis, not the original document.
          </p>
        </div>

        {missingGoalProfile ? (
          <div className="mt-6 rounded-md border border-amber/40 bg-amber/5 p-4 text-sm text-ink/80">
            You haven&apos;t set a target role yet.{" "}
            <Link href="/intake" className="focus-ring rounded-sm text-teal underline underline-offset-2">
              Complete the goal intake
            </Link>{" "}
            before continuing to analysis.
          </div>
        ) : null}

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDraggingOver(true);
          }}
          onDragLeave={() => setIsDraggingOver(false)}
          onDrop={handleDrop}
          className={`focus-ring mt-6 flex flex-col items-center justify-center rounded-md border-2 border-dashed px-6 py-12 text-center transition-colors ${
            isDraggingOver ? "border-teal bg-teal/5" : "border-ink/20"
          }`}
        >
          <p className="text-sm text-ink/70">Drag and drop files here</p>
          <p className="mt-1 text-xs text-ink/50">or</p>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="focus-ring mt-3 rounded border border-ink/25 px-4 py-2 text-sm font-medium text-ink hover:border-teal hover:text-teal"
          >
            Choose files
          </button>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ALLOWED_UPLOAD_MIME_TYPES.join(",")}
            onChange={(e) => {
              if (e.target.files?.length) addFiles(e.target.files);
              e.target.value = "";
            }}
            className="sr-only"
          />
        </div>

        {files.length > 0 ? (
          <ul className="mt-6 divide-y divide-ink/10 border-t border-b border-ink/10">
            {files.map((entry) => (
              <li key={entry.clientId} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">{entry.file.name}</p>
                  <p className="text-xs text-ink/50">{formatBytes(entry.file.size)}</p>
                  {entry.status === "rejected" && entry.rejectionReason ? (
                    <p className="mt-1 text-xs text-red">{entry.rejectionReason}</p>
                  ) : null}
                  {entry.status === "validated" && entry.validatedAt ? (
                    <p className="mt-1 text-xs text-ink/50">
                      Auto-deletes in {formatRemaining(entry.validatedAt, now)}
                    </p>
                  ) : null}
                </div>
                <div className="flex items-center gap-3">
                  <StatusPill status={entry.status} />
                  <button
                    type="button"
                    onClick={() => removeFile(entry.clientId)}
                    className="focus-ring rounded-sm text-xs text-ink/40 hover:text-red"
                    aria-label={`Remove ${entry.file.name}`}
                  >
                    Remove
                  </button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-6 text-sm text-ink/50">No files added yet.</p>
        )}

        {quotaExceeded ? (
          <div className="mt-6 rounded-md border border-amber/50 bg-amber/5 p-4">
            <h2 className="font-serif text-lg text-ink">You&apos;ve hit today&apos;s limit</h2>
            <p className="mt-1 text-sm text-ink/70">{quotaExceeded}</p>
          </div>
        ) : null}

        {createError ? (
          <div className="mt-6 rounded-md border border-red/40 bg-red/5 p-4">
            <h2 className="font-serif text-lg text-ink">Couldn&apos;t start the analysis</h2>
            <p className="mt-1 text-sm text-ink/70">{createError}</p>
            <button
              type="button"
              onClick={handleContinue}
              className="focus-ring mt-3 rounded border border-ink/25 px-4 py-2 text-sm text-ink hover:border-teal hover:text-teal"
            >
              Retry
            </button>
          </div>
        ) : null}

        <div className="mt-8 flex justify-end">
          <button
            type="button"
            onClick={handleContinue}
            disabled={!canContinue}
            className="focus-ring rounded border border-teal bg-teal px-6 py-3 text-sm font-medium text-cream disabled:cursor-not-allowed disabled:border-ink/15 disabled:bg-ink/10 disabled:text-ink/40"
          >
            {creating ? "Starting analysis…" : "Continue"}
          </button>
        </div>
      </main>
    </div>
  );
}

function StatusPill({ status }: { status: UploadStatus }) {
  const styles: Record<UploadStatus, string> = {
    pending: "border-ink/20 text-ink/50",
    uploading: "border-teal/40 text-teal",
    validated: "border-teal bg-teal/10 text-teal",
    rejected: "border-red/40 text-red",
  };
  const labels: Record<UploadStatus, string> = {
    pending: "Pending",
    uploading: "Uploading…",
    validated: "Validated",
    rejected: "Rejected",
  };
  return (
    <span className={`whitespace-nowrap rounded-sm border px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}
