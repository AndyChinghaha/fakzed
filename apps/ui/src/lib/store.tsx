"use client";

/** Server connection settings persisted in localStorage. */

import { createContext, useContext, useState } from "react";

export interface ServerSettings {
  baseUrl: string;
  apiKey: string;
}

const STORAGE_KEY = "fakzed.server";

const DEFAULT_SETTINGS: ServerSettings = {
  baseUrl: "http://127.0.0.1:8000",
  apiKey: "",
};

export function loadSettings(): ServerSettings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<ServerSettings>) };
  } catch {
    /* corrupted storage: fall back to defaults */
  }
  return DEFAULT_SETTINGS;
}

export function saveSettings(settings: ServerSettings): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

const SettingsContext = createContext<{
  settings: ServerSettings;
  setSettings: (next: ServerSettings) => void;
}>({ settings: DEFAULT_SETTINGS, setSettings: () => undefined });

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettingsState] = useState<ServerSettings>(() => loadSettings());

  const setSettings = (next: ServerSettings) => {
    setSettingsState(next);
    saveSettings(next);
  };

  return (
    <SettingsContext.Provider value={{ settings, setSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  return useContext(SettingsContext);
}
