"use client";

/** Chat debugger: streamed markdown replies with tool-call visualization.

The streamed assistant reply accumulates chunk by chunk; tool calls render as
collapsible steps. Sessions can be replayed by entering a session id.
*/

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { ApiError, FakzedClient } from "@/lib/api";
import type { ChatEvent } from "@/lib/types";
import { ErrorBanner, TypingDots } from "@/components/feedback";

interface ToolStep {
  name: string;
  result: string | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  toolSteps?: ToolStep[];
}

export default function ChatPanel({ client }: { client: FakzedClient }) {
  const searchParams = useSearchParams();
  const [agents, setAgents] = useState<{ name: string }[]>([]);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [agent, setAgent] = useState("");
  const [sessionId, setSessionId] = useState(searchParams.get("session") ?? "");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void client
      .listAgents()
      .then((list) => {
        setAgents(list);
        if (list.length > 0 && !agent) setAgent(list[0].name);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setAgentsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || !agent || streaming) return;
    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);

    const assistant: Message = { role: "assistant", content: "" };
    setMessages((prev) => [...prev, assistant]);
    setStreaming(true);

    const patchAssistant = (patch: Partial<Message>) => {
      setMessages((prev) => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        copy[copy.length - 1] = { ...last, ...patch };
        return copy;
      });
    };

    const onEvent = (event: ChatEvent) => {
      if (event.session_id) setSessionId(event.session_id);
      if (event.event === "chunk") {
        patchAssistant({ content: assistant.content + event.content });
        assistant.content += event.content;
      } else if (event.event === "tool_call_completed") {
        assistant.toolSteps = [
          ...(assistant.toolSteps ?? []),
          {
            name: event.tool_call?.name ?? "tool",
            result: event.tool_call_result ?? null,
          },
        ];
        patchAssistant({ toolSteps: assistant.toolSteps });
      }
    };

    try {
      const controller = new AbortController();
      abortRef.current = controller;
      await client.chatStream(agent, text, sessionId || undefined, onEvent, controller.signal);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        patchAssistant({ content: assistant.content || "（已中断）" });
      } else {
        setError(e instanceof ApiError ? e.message : String(e));
        // put the message back so the user can retry without retyping
        setInput(text);
      }
    } finally {
      abortRef.current = null;
      setStreaming(false);
    }
  };

  const stop = () => abortRef.current?.abort();

  return (
    <div className="flex h-full flex-col">
      {/* toolbar */}
      <div className="flex items-center gap-2 border-b border-zinc-800 bg-zinc-900/60 px-4 py-2">
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none"
        >
          {agentsLoading && <option value="">（加载中…）</option>}
          {!agentsLoading && agents.length === 0 && <option value="">（无 Agent）</option>}
          {agents.map((a) => (
            <option key={a.name} value={a.name}>
              {a.name}
            </option>
          ))}
        </select>
        <input
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          placeholder="会话 ID（留空新建，填入则恢复历史）"
          className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-zinc-500"
        />
      </div>

      {/* messages */}
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                message.role === "user"
                  ? "bg-zinc-100 text-zinc-900"
                  : "border border-zinc-800 bg-zinc-900/80 text-zinc-200"
              }`}
            >
              {message.role === "user" ? (
                <div className="whitespace-pre-wrap">{message.content}</div>
              ) : (
                <>
                  {message.toolSteps && message.toolSteps.length > 0 && (
                    <div className="mb-2 space-y-1">
                      {message.toolSteps.map((step, i) => (
                        <details
                          key={i}
                          className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1"
                        >
                          <summary className="cursor-pointer text-xs text-zinc-400">
                            🔧 {step.name}
                          </summary>
                          <pre className="mt-1 whitespace-pre-wrap text-[11px] text-zinc-500">
                            {step.result}
                          </pre>
                        </details>
                      ))}
                    </div>
                  )}
                  <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-pre:my-1">
                    {message.content ? <ReactMarkdown>{message.content}</ReactMarkdown> : streaming ? <TypingDots /> : "…"}
                  </div>
                </>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="px-4 pb-2">
          <ErrorBanner message={error} />
        </div>
      )}

      {/* composer */}
      <div className="flex items-end gap-2 border-t border-zinc-800 bg-zinc-900/60 p-3">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={2}
          placeholder={
            agentsLoading
              ? "正在连接平台…"
              : agent
                ? "输入消息，Enter 发送，Shift+Enter 换行"
                : "请先在 Agent 管理页注册一个 Agent"
          }
          className="flex-1 resize-none rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-zinc-500"
        />
        {streaming ? (
          <button
            onClick={stop}
            className="rounded bg-red-900 px-4 py-2 text-sm text-red-100 hover:bg-red-800"
          >
            中断
          </button>
        ) : (
          <button
            onClick={() => void send()}
            disabled={!agent || !input.trim()}
            className="rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 hover:bg-white disabled:opacity-40"
          >
            发送
          </button>
        )}
      </div>
    </div>
  );
}
