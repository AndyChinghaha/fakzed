"use client";

/** Monitoring: run list, metrics summary, and traces. */

import { useEffect, useState } from "react";
import { ApiError, FakzedClient } from "@/lib/api";
import type { MetricsSummary, RunInfo, TraceInfo } from "@/lib/types";

export default function MetricsPanel({ client }: { client: FakzedClient }) {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [traces, setTraces] = useState<TraceInfo[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setError(null);
      const [s, r, t] = await Promise.all([
        client.metricsSummary(),
        client.listRuns(),
        client.traces(),
      ]);
      setSummary(s);
      setRuns(r);
      setTraces(t);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stats = [
    { label: "总运行数", value: summary ? String(summary.runs) : "—" },
    { label: "输入 tokens", value: summary ? String(summary.total_input_tokens) : "—" },
    { label: "输出 tokens", value: summary ? String(summary.total_output_tokens) : "—" },
    { label: "工具调用", value: summary ? String(summary.total_tool_calls) : "—" },
    { label: "总成本 (USD)", value: summary ? `$${summary.total_cost_usd.toFixed(4)}` : "—" },
    { label: "平均延迟", value: summary ? `${summary.avg_latency_ms} ms` : "—" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-200">监控面板</h2>
        <button
          onClick={() => void refresh()}
          className="rounded bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-900 hover:bg-white"
        >
          刷新
        </button>
      </div>

      {error && <div className="text-xs text-red-300">错误：{error}</div>}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="text-[10px] text-zinc-500">{stat.label}</div>
            <div className="mt-1 text-lg font-semibold text-zinc-100">{stat.value}</div>
          </div>
        ))}
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold text-zinc-400">运行列表</h3>
        <div className="space-y-1">
          {runs.map((run) => (
            <div
              key={run.run_id}
              className="flex items-center gap-3 rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-xs"
            >
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${
                  run.status === "completed"
                    ? "bg-emerald-950 text-emerald-300"
                    : run.status === "failed"
                      ? "bg-red-950 text-red-300"
                      : "bg-amber-950 text-amber-300"
                }`}
              >
                {run.status}
              </span>
              <span className="text-zinc-300">{run.agent}</span>
              <span className="flex-1 truncate text-zinc-500">{run.input}</span>
              <span className="text-zinc-500">{run.run_id}</span>
            </div>
          ))}
          {runs.length === 0 && (
            <div className="text-xs text-zinc-600">暂无运行记录</div>
          )}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold text-zinc-400">最近 Trace</h3>
        <div className="space-y-2">
          {traces.map((trace) => (
            <details
              key={trace.trace_id}
              className="rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2"
            >
              <summary className="cursor-pointer text-xs text-zinc-300">
                {trace.trace_id}
              </summary>
              <div className="mt-2 space-y-1">
                {trace.spans.map((span, i) => (
                  <div key={i} className="flex justify-between text-[11px] text-zinc-500">
                    <span>{span.name}</span>
                    <span>
                      {span.attributes.agent ? `${span.attributes.agent} · ` : ""}
                      {span.started_at != null && span.ended_at != null
                        ? `${((span.ended_at - span.started_at) * 1000).toFixed(1)}ms`
                        : ""}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          ))}
          {traces.length === 0 && (
            <div className="text-xs text-zinc-600">暂无 trace</div>
          )}
        </div>
      </div>
    </div>
  );
}
