/** REST + SSE client for the fakzed-server API. */

import type {
  AgentInfo,
  ApiKeyInfo,
  ChatEvent,
  MetricsSummary,
  OrgInfo,
  ProjectInfo,
  RunInfo,
  SessionInfo,
  TraceInfo,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface ServerConfig {
  baseUrl: string;
  apiKey: string;
}

export class FakzedClient {
  constructor(private config: ServerConfig) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.config.baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.config.apiKey,
        ...(init.headers ?? {}),
      },
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }

  // -- agents ---------------------------------------------------------------

  listAgents(): Promise<AgentInfo[]> {
    return this.request<AgentInfo[]>("/api/agents");
  }

  createAgent(payload: {
    name: string;
    model: string;
    description?: string;
    instructions?: string;
  }): Promise<AgentInfo> {
    return this.request<AgentInfo>("/api/agents", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  setAgentEnabled(name: string, enabled: boolean): Promise<AgentInfo> {
    return this.request<AgentInfo>(`/api/agents/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify({ enabled }),
    });
  }

  deleteAgent(name: string): Promise<{ unregistered: boolean }> {
    return this.request(`/api/agents/${encodeURIComponent(name)}`, { method: "DELETE" });
  }

  // -- chat -----------------------------------------------------------------

  chat(name: string, message: string, sessionId?: string): Promise<ChatEvent> {
    return this.request<ChatEvent>(`/api/agents/${encodeURIComponent(name)}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId ?? null }),
    });
  }

  resume(name: string): Promise<ChatEvent> {
    return this.request<ChatEvent>(`/api/agents/${encodeURIComponent(name)}/resume`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  }

  /** Stream chat events via SSE; `onEvent` is called for each parsed event. */
  async chatStream(
    name: string,
    message: string,
    sessionId: string | undefined,
    onEvent: (event: ChatEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(
      `${this.config.baseUrl}/api/agents/${encodeURIComponent(name)}/chat/stream`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": this.config.apiKey,
        },
        body: JSON.stringify({ message, session_id: sessionId ?? null }),
        signal,
      },
    );
    if (!response.ok || !response.body) {
      throw new ApiError(response.status, `stream failed: ${response.statusText}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (line.startsWith("data:")) {
          const payload = line.slice(5).trim();
          if (payload) onEvent(JSON.parse(payload) as ChatEvent);
        }
      }
    }
  }

  // -- sessions ---------------------------------------------------------------

  getSession(sessionId: string): Promise<SessionInfo> {
    return this.request<SessionInfo>(`/api/sessions/${encodeURIComponent(sessionId)}`);
  }

  // -- runs -------------------------------------------------------------------

  listRuns(): Promise<RunInfo[]> {
    return this.request<RunInfo[]>("/api/runs");
  }

  createRun(agent: string, message: string, sessionId?: string): Promise<RunInfo> {
    return this.request<RunInfo>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ agent, message, session_id: sessionId ?? null }),
    });
  }

  cancelRun(runId: string): Promise<{ cancelled: boolean }> {
    return this.request(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
  }

  // -- monitoring ---------------------------------------------------------------

  metricsSummary(): Promise<MetricsSummary> {
    return this.request<MetricsSummary>("/api/metrics/summary");
  }

  traces(): Promise<TraceInfo[]> {
    return this.request<TraceInfo[]>("/api/traces");
  }

  // -- tenancy ------------------------------------------------------------------

  listOrgs(): Promise<OrgInfo[]> {
    return this.request<OrgInfo[]>("/api/tenants/orgs");
  }

  createOrg(name: string): Promise<OrgInfo> {
    return this.request<OrgInfo>("/api/tenants/orgs", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
  }

  listProjects(orgId: string): Promise<ProjectInfo[]> {
    return this.request<ProjectInfo[]>(`/api/tenants/orgs/${encodeURIComponent(orgId)}/projects`);
  }

  createProject(name: string, orgId?: string): Promise<ProjectInfo> {
    return this.request<ProjectInfo>("/api/tenants/projects", {
      method: "POST",
      body: JSON.stringify({ name, org_id: orgId ?? null }),
    });
  }

  // -- api keys --------------------------------------------------------------------

  issueKey(name: string, role = "user"): Promise<ApiKeyInfo> {
    return this.request<ApiKeyInfo>("/api/keys", {
      method: "POST",
      body: JSON.stringify({ name, role }),
    });
  }

  revokeKey(keyId: string): Promise<{ revoked: boolean }> {
    return this.request(`/api/keys/${encodeURIComponent(keyId)}`, { method: "DELETE" });
  }
}
