"use client";

/** A FakzedClient bound to the current server settings. */

import { useMemo } from "react";
import { FakzedClient } from "./api";
import { useSettings } from "./store";

export function useClient(): FakzedClient {
  const { settings } = useSettings();
  return useMemo(
    () => new FakzedClient({ baseUrl: settings.baseUrl, apiKey: settings.apiKey }),
    [settings.baseUrl, settings.apiKey],
  );
}
