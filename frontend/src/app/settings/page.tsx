import type { Metadata } from "next";
import { PreferencesPage } from "@/features/preferences/preferences-page";

export const metadata: Metadata = { title: "Réglages" };

export default function Page() {
  return <PreferencesPage />;
}
