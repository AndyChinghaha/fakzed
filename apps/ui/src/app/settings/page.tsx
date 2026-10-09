"use client";

/** Settings: API keys and tenancy. */

import ApiKeyPanel from "@/components/ApiKeyPanel";
import { useClient } from "@/lib/useClient";

export default function SettingsPage() {
  const client = useClient();
  return (
    <div className="max-w-2xl space-y-8">
      <ApiKeyPanel client={client} />
      <div className="space-y-2">
        <h2 className="text-sm font-semibold text-zinc-200">说明</h2>
        <p className="text-xs text-zinc-500">
          平台地址与 API Key 保存在浏览器 localStorage 中。fakzed-server 默认在
          <code className="text-zinc-400"> http://127.0.0.1:8000 </code>
          启动，可用
          <code className="text-zinc-400"> --admin-key </code>
          指定管理员 Key，或使用本页签发的 admin Key。
        </p>
      </div>
    </div>
  );
}
