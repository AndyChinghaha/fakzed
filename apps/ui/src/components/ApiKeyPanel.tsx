"use client";

/** User & API key management (admin role required). */

import { useState } from "react";
import { ApiError, FakzedClient } from "@/lib/api";
import type { ApiKeyInfo } from "@/lib/types";
import { ErrorBanner, Spinner } from "@/components/feedback";

export default function ApiKeyPanel({ client }: { client: FakzedClient }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("user");
  const [issued, setIssued] = useState<ApiKeyInfo | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const issue = async () => {
    try {
      setError(null);
      setIssuing(true);
      setIssued(await client.issueKey(name.trim() || "ui-key", role));
      setName("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setIssuing(false);
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-zinc-200">API Key 管理</h2>
      <p className="text-xs text-zinc-500">
        需要 admin 角色的 API Key。签发后原文仅显示一次，请妥善保存。
      </p>

      {error && <ErrorBanner message={error} />}

      <div className="flex items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Key 名称"
          className="w-48 rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-zinc-500"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 outline-none"
        >
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <button
          onClick={() => void issue()}
          disabled={issuing}
          className="flex items-center gap-2 rounded bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-40"
        >
          {issuing && <Spinner className="h-3 w-3 border-zinc-400 border-t-zinc-900" />}
          {issuing ? "签发中…" : "签发"}
        </button>
      </div>

      {issued?.api_key && (
        <div className="rounded border border-emerald-900 bg-emerald-950/40 p-3 space-y-2">
          <div className="text-xs text-emerald-300">Key 已签发（仅此一次展示）：</div>
          <code className="block select-all break-all rounded bg-zinc-950 px-2 py-1.5 text-xs text-emerald-200">
            {issued.api_key}
          </code>
          <div className="text-[11px] text-zinc-500">
            也可复制到顶部「API Key」输入框使用。
          </div>
        </div>
      )}
    </div>
  );
}
