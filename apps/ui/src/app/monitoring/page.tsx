"use client";

/** Monitoring page. */

import MetricsPanel from "@/components/MetricsPanel";
import { useClient } from "@/lib/useClient";

export default function MonitoringPage() {
  const client = useClient();
  return <MetricsPanel client={client} />;
}
