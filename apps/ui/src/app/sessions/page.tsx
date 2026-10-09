"use client";

/** Session management page. */

import SessionList from "@/components/SessionList";
import { useClient } from "@/lib/useClient";

export default function SessionsPage() {
  const client = useClient();
  return <SessionList client={client} />;
}
