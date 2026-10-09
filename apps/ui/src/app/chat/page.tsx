"use client";

/** Chat debugger page. */

import { Suspense } from "react";
import ChatPanel from "@/components/ChatPanel";
import { useClient } from "@/lib/useClient";

export default function ChatPage() {
  const client = useClient();
  return (
    <div className="h-full">
      <Suspense fallback={<div className="text-xs text-zinc-500">加载中…</div>}>
        <ChatPanel client={client} />
      </Suspense>
    </div>
  );
}
