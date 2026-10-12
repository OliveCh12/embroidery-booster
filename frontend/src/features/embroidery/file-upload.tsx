"use client";

import { Alert, Button, Card } from "@heroui/react";
import { CheckCircle2, ImagePlus, Upload, X } from "lucide-react";
import { useId, useRef, useState, type ReactNode } from "react";
import { ACCEPTED_FILES, clipboardFile } from "./file-import";

export function FileUpload({ file, onSelect, onClear, disabled, error, headerContent, children }: {
  file: File | null; onSelect: (file: File) => void; onClear: () => void; disabled: boolean;
  error: string | null; headerContent?: ReactNode; children: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);
  const hintId = useId();
  const [dragging, setDragging] = useState(false);
  const [pasteError, setPasteError] = useState<string | null>(null);
  const importError = error ?? pasteError;

  function select(selected: File) {
    setPasteError(null);
    onSelect(selected);
  }

  return (
    <div role="region" aria-label="Import et aperçu du dessin" aria-describedby={hintId} aria-keyshortcuts="Control+V Meta+V"
      tabIndex={0} className="relative flex min-h-0 flex-1 flex-col rounded-2xl outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background"
      onClick={event => { if (!(event.target as HTMLElement).closest("button, a, input, [role=tab]")) event.currentTarget.focus({ preventScroll: true }); }}
      onKeyDown={event => { if (event.target === event.currentTarget && !disabled && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); input.current?.click(); } }}
      onPaste={event => {
        if (disabled) return;
        const selected = clipboardFile(event.clipboardData);
        if (selected) { event.preventDefault(); select(selected); }
        else setPasteError("Copiez une image ou un fichier, puis collez-le ici avec Ctrl+V ou ⌘V.");
      }}
      onDragEnter={event => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        if (!disabled) { dragDepth.current++; setDragging(true); }
      }}
      onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); event.dataTransfer.dropEffect = disabled ? "none" : "copy"; } }}
      onDragLeave={() => { dragDepth.current = Math.max(0, dragDepth.current - 1); if (!dragDepth.current) setDragging(false); }}
      onDrop={event => {
        event.preventDefault(); dragDepth.current = 0; setDragging(false);
        const selected = event.dataTransfer.files[0];
        if (selected && !disabled) select(selected);
      }}>
      <input ref={input} type="file" className="hidden" aria-label="Fichier à broder" disabled={disabled} accept={ACCEPTED_FILES}
        onChange={event => { const selected = event.target.files?.[0]; if (selected) select(selected); event.target.value = ""; }} />
      <Card className="@container min-h-[400px] flex-1 gap-4 md:min-h-0">
        <Card.Header className="shrink-0 flex-row flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 items-center gap-4">
            {file && <CheckCircle2 size={18} className="shrink-0 text-success" aria-label="Fichier chargé" />}
            <Card.Title className="min-w-0 truncate" title={file?.name}>{file?.name ?? "Aperçu"}</Card.Title>
          </div>
          {headerContent}
          {file && <div className="flex shrink-0 items-center gap-4">
            <Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => input.current?.click()}><Upload size={15} />Remplacer</Button>
            <Button size="sm" variant="ghost" isIconOnly aria-label="Retirer le fichier" isDisabled={disabled} onPress={() => { setPasteError(null); onClear(); }}><X size={15} /></Button>
          </div>}
        </Card.Header>
        <Card.Content className="flex min-h-0 flex-1 flex-col gap-4">
          {importError && <Alert status="danger" className="shrink-0"><Alert.Indicator /><Alert.Content><Alert.Title>Import impossible</Alert.Title><Alert.Description>{importError}</Alert.Description></Alert.Content></Alert>}
          {file ? children : <div className={`flex min-h-64 flex-1 flex-col items-center justify-center gap-4 rounded-xl border border-dashed p-4 text-center transition-colors hover:border-accent hover:bg-accent-soft/30 ${importError ? "border-danger" : "border-border"}`}>
            <span className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent"><ImagePlus size={28} aria-hidden="true" /></span>
            <div className="flex flex-col gap-4">
              <p className="text-base font-medium text-foreground">Déposez votre dessin</p>
              <p className="text-sm text-muted">SVG, PNG ou image · 10 Mio maximum</p>
            </div>
            <Button variant="primary" isDisabled={disabled} onPress={() => input.current?.click()}><Upload size={16} />Choisir un fichier</Button>
            <p id={hintId} className="max-w-sm text-xs leading-relaxed text-muted">Ou cliquez ici et collez une image avec <kbd className="font-medium text-foreground">Ctrl+V</kbd> / <kbd className="font-medium text-foreground">⌘V</kbd>.</p>
          </div>}
          {file && <p id={hintId} className="shrink-0 text-xs text-muted">Déposez un autre fichier ou cliquez dans l’aperçu pour coller une image · {Math.ceil(file.size / 1024)} Ko.</p>}
        </Card.Content>
      </Card>
      {dragging && !disabled && <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-accent bg-surface/95 p-4 text-center text-accent" role="status">
        <Upload size={32} aria-hidden="true" /><p className="font-medium">{file ? "Déposez pour remplacer le dessin" : "Déposez pour importer le dessin"}</p>
      </div>}
    </div>
  );
}
