"use client";

import { Chip, buttonVariants } from "@heroui/react";
import { Spline } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCapabilities } from "@/features/embroidery/use-capabilities";
import { ThemeMenu } from "./theme-menu";

export function AppHeader() {
  const path = usePathname();
  const capabilities = useCapabilities();
  return (
    <header className="shrink-0 border-b border-border bg-surface">
      <div className="flex min-h-16 items-center gap-4 px-4">
        <Link href="/" className="mr-auto flex shrink-0 items-center gap-4 font-semibold tracking-tight" aria-label="Embroidery Booster · Atelier">
          <Spline size={22} className="text-accent" /><span className="hidden sm:inline">Embroidery Booster</span>
        </Link>
        <nav aria-label="Navigation principale" className="flex gap-4">
          {[{ href: "/", label: "Atelier" }, { href: "/quality", label: "Comparaison" }].map(item => (
            <Link key={item.href} href={item.href} aria-current={path === item.href ? "page" : undefined}
              className={buttonVariants({ variant: path === item.href ? "secondary" : "ghost", size: "sm" })}>
              {item.label}
            </Link>
          ))}
        </nav>
        <Chip size="sm" variant="soft" color={capabilities.isError ? "warning" : capabilities.data ? "success" : "default"} className="hidden lg:inline-flex">
          {capabilities.isError ? "Moteur indisponible" : capabilities.data ? "Prêt à générer" : "Connexion…"}
        </Chip>
        <ThemeMenu />
      </div>
    </header>
  );
}
