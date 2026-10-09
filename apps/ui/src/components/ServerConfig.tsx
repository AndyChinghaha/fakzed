"use client";

/** Server URL + API key editor, persisted to localStorage. */

import { useState } from "react";
import { useSettings } from "@/lib/store";

export default function ServerConfig() {
  const { settings, setSettings } = useSettings();
  const [baseUrl, setBaseUrl] = useState(settings.baseUrl);
  const [apiKey, setApiKey] = useState(settings.apiKey);
  const [saved, setSaved] = useState(false);

  const apply = () => {
    setSettings({ baseUrl: baseUrl.replace(/\/+$/, ""), apiKey });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2">
      <label className="text-xs text-zinc-500 shrink-0">平台地址</label>
      <input
        value={baseUrl}
        onChange={(e) => setBaseUrl(e.target.value)}
        placeholder="http://127.0.0.1:8000"
        className="w-64 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-500"
      />
      <label className="text-xs text-zinc-500 shrink-0">API Key</label>
      <input
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        type="password"
        placeholder="X-API-Key"
        className="w-56 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-500"
      />
      <button
        onClick={apply}
        className="rounded bg-zinc-100 px-3 py-1 text-xs font-medium text-zinc-900 hover:bg-white"
      >
        {saved ? "已保存" : "连接"}
      </button>
    </div>
  );
}
