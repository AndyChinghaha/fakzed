"use client";

/** Session management: resume a historical conversation in the chat page. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, FakzedClient } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

export default function SessionList({ client }: { client: FakzedClient }) {
  const [sessionId, setSessionId] = useState("");
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (id: string) => {
    try {
      setError(null);
      setSession(await client.getSession(id));
    } catch (e) {
      setSession(null);
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  useEffect(() => {
    if (sessionId.trim()) void load(sessionId.trim());
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-2 text-sm font-semibold text-zinc-200">会话恢复</h2>
        <input
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          placeholder="输入会话 ID 查看详情"
          className="w-full rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-500"
        />
        <p className="mt-2 text-xs text-zinc-500">
          在对话页粘贴同一会话 ID，即可从上次的上下文继续。
        </p>
      </div>

      {error && <div className="text-xs text-red-300">错误：{error}</div>}

      {session && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs text-zinc-400">
              {session.messages.length} 条消息 · 更新于{" "}
              {new Date(session.updated_at).toLocaleString()}
            </div>
            <Link
              href={`/chat?session=${session.session_id}`}
              className="rounded bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-900 hover:bg-white"
            >
              在对话页恢复
            </Link>
          </div>
          {session.messages.map((message, index) => (
            <div
              key={index}
              className={`rounded border px-3 py-2 text-sm ${
                message.role === "user"
                  ? "border-zinc-800 bg-zinc-900/40 text-zinc-300"
                  : "border-zinc-800/60 bg-zinc-950 text-zinc-400"
              }`}
            >
              <span className="mr-2 text-[10px] uppercase text-zinc-600">
                {message.role}
              </span>
              <span className="whitespace-pre-wrap">{message.content}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
