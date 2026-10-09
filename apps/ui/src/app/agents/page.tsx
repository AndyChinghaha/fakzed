"use client";

/** Agent management page. */

import AgentList from "@/components/AgentList";
import { useClient } from "@/lib/useClient";

export default function AgentsPage() {
  const client = useClient();
  return <AgentList client={client} />;
}
