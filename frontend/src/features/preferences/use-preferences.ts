"use client";

import { useMemo, useSyncExternalStore } from "react";
import { parsePreferences, PREFS_STORAGE_KEY, type AppPreferences } from "./preferences";

function readPreferences() {
  try { return window.localStorage.getItem(PREFS_STORAGE_KEY); }
  catch { return null; }
}

function subscribe(callback: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === PREFS_STORAGE_KEY || event.key === null) callback();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(PREFS_STORAGE_KEY, callback);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(PREFS_STORAGE_KEY, callback);
  };
}

export function usePreferences() {
  const raw = useSyncExternalStore(subscribe, readPreferences, () => undefined);
  const preferences = useMemo(() => parsePreferences(raw ?? null), [raw]);
  return { preferences, ready: raw !== undefined };
}

export function savePreferences(preferences: AppPreferences) {
  try {
    window.localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(preferences));
    window.dispatchEvent(new Event(PREFS_STORAGE_KEY));
    return true;
  } catch { return false; }
}
