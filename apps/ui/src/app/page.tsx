"use client";

/** Dashboard: agent overview + metrics summary. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { useClient } from "@/lib/useClient";
import type { AgentInfo, MetricsSummary } from "@/lib/types";

export default function DashboardPage() {
  const client = useClient();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([client.listAgents(), client.metricsSummary()])
      .then(([a, s]) => {
        setAgents(a);
        setSummary(s);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [client]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-zinc-50">仪表盘</h1>
        <p className="text-xs text-zinc-500">fakzed 平台总览</p>
      </div>

      {error && (
        <div className="rounded border border-amber-900 bg-amber-950/40 px-3 py-2 text-xs text-amber-300">
          无法连接平台：{error}
          <div className="mt-1">
            请确认顶部「平台地址」正确，且 fakzed-server 已启动（
            <code className="text-amber-200">uv run fakzed-server --admin-key ...</code>
            ）。
          </div>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-[10px] text-zinc-500">Agent 总数</div>
          <div className="mt-1 text-2xl font-bold text-zinc-50">{agents.length}</div>
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-[10px] text-zinc-500">总运行数</div>
          <div className="mt-1 text-2xl font-bold text-zinc-50">{summary?.runs ?? "—"}</div>
        </div>
        <div className="rounded border border-zinc-800 bg-zinc-900/60 p-4">
          <div className="text-[10px] text-zinc-500">总成本 (USD)</div>
          <div className="mt-1 text-2xl font-bold text-zinc-50">
            {summary ? `$${summary.total_cost_usd.toFixed(4)}` : "—"}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200">已注册 Agent</h2>
          <Link href="/chat" className="text-xs text-zinc-400 hover:text-zinc-200">
            去对话调试 →
          </Link>
        </div>
        {agents.map((agent) => (
          <div
            key={agent.name}
            className="flex items-center gap-3 rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                agent.enabled ? "bg-emerald-400" : "bg-zinc-600"
              }`}
            />
            <span className="text-sm text-zinc-200">{agent.name}</span>
            <span className="text-xs text-zinc-500">{agent.description ?? agent.kind}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
