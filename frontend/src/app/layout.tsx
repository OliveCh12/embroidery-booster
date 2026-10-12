import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppHeader } from "@/components/layout/app-header";
import { AppFooter } from "@/components/layout/app-footer";
import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Atelier · Embroidery Booster", template: "%s · Embroidery Booster" },
  description: "Votre atelier de broderie : SVG, images et points machine PES / DST.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr" suppressHydrationWarning>
      <body className="bg-background text-foreground antialiased">
        <Providers>
          <div className="flex min-h-dvh flex-col gap-4 md:h-dvh md:overflow-hidden">
            <a href="#workspace" className="sr-only z-50 rounded-lg bg-surface focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:p-4">Aller au contenu</a>
            <AppHeader />
            <main id="workspace" tabIndex={-1} className="flex min-h-0 w-full flex-1 flex-col px-4 outline-none md:overflow-hidden">
              {children}
            </main>
            <AppFooter />
          </div>
        </Providers>
      </body>
    </html>
  );
}
