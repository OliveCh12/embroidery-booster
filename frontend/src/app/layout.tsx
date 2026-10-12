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
          <div className="flex min-h-dvh flex-col gap-4">
            <a href="#workspace" className="sr-only focus:not-sr-only focus:p-3">Aller au contenu</a>
            <AppHeader />
            <main id="workspace" className="mx-auto w-full max-w-[1440px] flex-1 px-4">
              {children}
            </main>
            <AppFooter />
          </div>
        </Providers>
      </body>
    </html>
  );
}
