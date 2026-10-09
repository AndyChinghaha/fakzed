"use client";

/** Shared feedback primitives: spinner, error banner, empty state, loading. */

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

interface EmptyStateProps {
  title: string;
  hint?: string;
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-label="加载中"
      className={`inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-500 border-t-zinc-200 ${className}`}
    />
  );
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="flex items-center justify-between gap-3 rounded border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
      <span>错误：{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="shrink-0 rounded border border-red-800 px-2 py-0.5 text-[11px] text-red-200 hover:bg-red-900/60"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: EmptyStateProps) {
  return (
    <div className="col-span-full rounded border border-dashed border-zinc-800 px-4 py-8 text-center">
      <div className="text-sm text-zinc-400">{title}</div>
      {hint && <div className="mt-1 text-xs text-zinc-600">{hint}</div>}
    </div>
  );
}

export function LoadingBlock({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 rounded border border-zinc-800/60 bg-zinc-900/40 px-4 py-6 text-xs text-zinc-500">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

export function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="正在生成">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500 [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500 [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-500 [animation-delay:300ms]" />
    </span>
  );
}
