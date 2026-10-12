"use client";

import { Button, Card } from "@heroui/react";
import { FileImage, Upload, X } from "lucide-react";
import { useRef, useState } from "react";

export function FileUpload({ file, onSelect, onClear, disabled }: {
  file: File | null; onSelect: (file: File) => void; onClear: () => void; disabled: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  return (
    <Card className="shrink-0 gap-4">
      <Card.Header><Card.Title>Dessin</Card.Title></Card.Header>
      <Card.Content className="gap-4">
        <input ref={input} type="file" className="hidden" aria-label="Fichier à broder" disabled={disabled}
          accept=".svg,.png,.jpg,.jpeg,.webp,.bmp,.gif,.tif,.tiff,.pdf,.eps,.ps,.ai"
          onChange={event => { const selected = event.target.files?.[0]; if (selected) onSelect(selected); event.target.value = ""; }} />
        <div className={`flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed p-4 text-center ${dragging ? "border-accent bg-accent-soft" : "border-border"}`}
          onDragOver={event => { event.preventDefault(); if (!disabled) setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={event => { event.preventDefault(); setDragging(false); const selected = event.dataTransfer.files[0]; if (selected && !disabled) onSelect(selected); }}>
          {!file && <FileImage size={27} className="text-muted" />}
          {file ? <div className="max-w-full"><p className="truncate text-sm font-medium">{file.name}</p><p className="mt-1 text-xs text-muted">{Math.ceil(file.size / 1024)} Ko</p></div>
            : <p className="text-sm text-muted">Glissez votre dessin ici</p>}
          <div className="flex items-center gap-4">
            <Button size="sm" variant="secondary" isDisabled={disabled} onPress={() => input.current?.click()}>
              <Upload size={15} />{file ? "Changer de fichier" : "Importer un fichier"}
            </Button>
            {file && <Button size="sm" variant="ghost" isIconOnly aria-label="Retirer le fichier" isDisabled={disabled} onPress={onClear}><X size={15} /></Button>}
          </div>
        </div>
        <p className="text-xs leading-relaxed text-muted">SVG ou image · 10 Mio maximum.<br />Le moteur automatique sépare les couleurs en régions à broder.</p>
      </Card.Content>
    </Card>
  );
}
