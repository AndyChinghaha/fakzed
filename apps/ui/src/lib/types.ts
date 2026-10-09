/** Shared shapes mirroring the fakzed-server API. */

export interface AgentInfo {
  name: string;
  kind: string;
  description: string | null;
  project_id: string;
  enabled: boolean;
}

export interface ChatEvent {
  event: string;
  content: string;
  reasoning_content?: string | null;
  tool_call?: { id: string; name: string; arguments: Record<string, unknown> } | null;
  tool_call_result?: string | null;
  session_id?: string | null;
  usage?: { input_tokens?: number | null; output_tokens?: number | null } | null;
}

export interface SessionInfo {
  session_id: string;
  name?: string | null;
  user_id?: string | null;
  messages: {
    role: string;
    content: string;
    tool_calls?: unknown[] | null;
    created_at?: string | null;
  }[];
  created_at: string;
  updated_at: string;
}

export interface RunInfo {
  run_id: string;
  agent: string;
  status: string;
  input?: string | null;
  output?: string | null;
  error?: string | null;
}

export interface MetricsSummary {
  runs: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tool_calls: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

export interface TraceSpan {
  trace_id: string;
  span_id: string;
  parent_id?: string | null;
  name: string;
  attributes: Record<string, string>;
  started_at?: number | null;
  ended_at?: number | null;
}

export interface TraceInfo {
  trace_id: string;
  spans: TraceSpan[];
}

export interface ApiKeyInfo {
  key_id: string;
  name: string;
  user_id: string;
  role: string;
  created_at: string;
  api_key?: string;
}

export interface OrgInfo {
  org_id: string;
  name: string;
}

export interface ProjectInfo {
  project_id: string;
  org_id: string;
  name: string;
}
