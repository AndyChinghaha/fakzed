"use client";

/** Agent management: list, toggle enabled, create from config. */

import { useEffect, useState } from "react";
import { ApiError, FakzedClient } from "@/lib/api";
import { useSettings } from "@/lib/store";
import type { AgentInfo } from "@/lib/types";

export default function AgentList({ client }: { client: FakzedClient }) {
  const { settings } = useSettings();
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", model: "", description: "", instructions: "" });

  const refresh = async () => {
    try {
      setError(null);
      setAgents(await client.listAgents());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.baseUrl, settings.apiKey]);

  const toggle = async (agent: AgentInfo) => {
    try {
      await client.setAgentEnabled(agent.name, !agent.enabled);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const create = async () => {
    try {
      setError(null);
      await client.createAgent({
        name: form.name,
        model: form.model,
        description: form.description || undefined,
        instructions: form.instructions || undefined,
      });
      setForm({ name: "", model: "", description: "", instructions: "" });
      setCreating(false);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-zinc-200">
          已注册 Agent（{agents.length}）
        </h2>
        <button
          onClick={() => setCreating((v) => !v)}
          className="rounded bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white"
        >
          {creating ? "取消" : "创建 Agent"}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {creating && (
        <div className="rounded border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="名称（如 support-bot）"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
          />
          <input
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
            placeholder="模型（provider:model，如 deepseek:deepseek-chat）"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
          />
          <input
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="描述（可选）"
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
          />
          <textarea
            value={form.instructions}
            onChange={(e) => setForm({ ...form, instructions: e.target.value })}
            placeholder="系统指令（可选）"
            rows={3}
            className="w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
          />
          <button
            onClick={() => void create()}
            disabled={!form.name || !form.model}
            className="rounded bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-40"
          >
            注册到平台
          </button>
        </div>
      )}

      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <div
            key={agent.name}
            className="rounded border border-zinc-800 bg-zinc-900/60 p-3 space-y-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-zinc-100 text-sm">{agent.name}</span>
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] ${
                  agent.enabled
                    ? "bg-emerald-950 text-emerald-300"
                    : "bg-zinc-800 text-zinc-400"
                }`}
              >
                {agent.enabled ? "运行中" : "已停用"}
              </span>
            </div>
            <div className="text-xs text-zinc-500">
              {agent.description || agent.kind} · {agent.project_id}
            </div>
            <button
              onClick={() => void toggle(agent)}
              className={`w-full rounded px-2 py-1 text-xs ${
                agent.enabled
                  ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                  : "bg-emerald-900 text-emerald-200 hover:bg-emerald-800"
              }`}
            >
              {agent.enabled ? "停用" : "启用"}
            </button>
          </div>
        ))}
        {agents.length === 0 && !error && (
          <div className="text-xs text-zinc-500 col-span-full">
            还没有 Agent。启动 fakzed-server 并在代码中 server.register(...)，或点「创建 Agent」。
          </div>
        )}
      </div>
    </div>
  );
}
