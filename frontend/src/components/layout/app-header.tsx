"use client";

import { buttonVariants } from "@heroui/react";
import { BadgeCheck, Frame, GitFork, Settings, Spline } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import packageInfo from "../../../package.json";
import { ThemeMenu } from "./theme-menu";

export function AppHeader() {
  const path = usePathname();
  const version = packageInfo.version;
  return (
    <header className="shrink-0 border-b border-border bg-surface">
      <div className="flex min-h-16 items-center gap-2 px-3 sm:gap-4 sm:px-4">
        <Link href="/" className="mr-auto flex shrink-0 items-center gap-2 font-semibold tracking-tight md:gap-4" aria-label={`Embroidery Booster · version ${version} · Atelier`}>
          <Spline size={22} className="text-accent" aria-hidden="true" />
          <span className="flex items-baseline gap-2">
            <span className="hidden md:inline">Embroidery Booster</span>
            <span className="text-xs font-normal tracking-normal text-muted" title="Version de l’application">v{version}</span>
          </span>
        </Link>
        <nav aria-label="Navigation principale" className="flex shrink-0 gap-2 sm:gap-4">
          {[{ href: "/", label: "Atelier", icon: Frame }, { href: "/quality", label: "Qualité", icon: BadgeCheck }].map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} aria-label={label} aria-current={path === href ? "page" : undefined}
              className={`${buttonVariants({ variant: path === href ? "secondary" : "ghost", size: "sm" })} w-9 px-0 sm:w-auto sm:px-3`}>
              <Icon size={16} className="sm:hidden" aria-hidden="true" /><span className="hidden sm:inline">{label}</span>
            </Link>
          ))}
          <Link href="/settings" aria-label="Réglages" aria-current={path === "/settings" ? "page" : undefined}
            className={`${buttonVariants({ variant: path === "/settings" ? "secondary" : "ghost", size: "sm" })} w-9 px-0 md:w-auto md:px-3`}>
            <Settings size={16} aria-hidden="true" /><span className="hidden md:inline">Réglages</span>
          </Link>
          <a href="https://github.com/OliveCh12/embroidery-booster" target="_blank" rel="noopener noreferrer" aria-label="Contribuer sur GitHub · nouvel onglet"
            className={`${buttonVariants({ variant: "ghost", size: "sm" })} w-9 px-0 md:w-auto md:px-3`}>
            <GitFork size={16} aria-hidden="true" /><span className="hidden md:inline">Contribuer</span>
          </a>
        </nav>
        <ThemeMenu />
      </div>
    </header>
  );
}
