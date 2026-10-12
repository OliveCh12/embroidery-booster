import { ArrowUpRight } from "lucide-react";

export function AppFooter() {
  return (
    <footer className="shrink-0 border-t border-border text-xs text-muted">
      <div className="flex flex-wrap items-center justify-between gap-4 p-4">
        <span>Embroidery Booster</span>
        <span>Validez le rendu par un essai sur votre tissu.</span>
        <a href="https://github.com/OliveCh12/embroidery-booster" target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 hover:text-foreground">
          Code source <ArrowUpRight size={13} />
        </a>
      </div>
    </footer>
  );
}
