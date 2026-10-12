"use client";

import { Alert, Button } from "@heroui/react";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, apiRequest } from "@/lib/api";
import { FileUpload } from "./file-upload";
import { ResultPane } from "./results";
import { DEFAULT_SETTINGS, generationForm, validateFile } from "./settings";
import { SettingsForm } from "./settings-form";
import type { GenerationResult } from "./types";
import { useCapabilities } from "./use-capabilities";

export function EmbroideryWorkspace() {
  const capabilities = useCapabilities();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const generation = useMutation({
    mutationFn: async ({ file, settings }: { file: File; settings: typeof DEFAULT_SETTINGS }) => {
      const result = await apiRequest<GenerationResult>("/api/convert", { method: "POST", body: generationForm(file, settings) });
      if (!result.success) throw new ApiError("Le moteur n’a pas produit de résultat.", 200);
      return result;
    },
    retry: false,
  });

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function selectFile(selected: File | null) {
    if (generation.isPending) return;
    generation.reset();
    const error = selected ? validateFile(selected) : null;
    setFileError(error);
    setFile(error ? null : selected);
    setPreview(selected && !error && /\.(svg|png|jpe?g|webp|bmp|gif)$/i.test(selected.name) ? URL.createObjectURL(selected) : null);
  }

  const error = fileError ?? generation.error?.message;
  return <div className="grid items-start gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
    <aside className="flex min-w-0 flex-col gap-4" aria-label="Préparation de la broderie">
      <FileUpload file={file} onSelect={selectFile} onClear={() => selectFile(null)} disabled={generation.isPending} />
      <SettingsForm settings={settings} onChange={setSettings} capabilities={capabilities.data}
        busy={generation.isPending} canGenerate={!!file && !!capabilities.data && !capabilities.isError}
        onSubmit={() => { if (file) generation.mutate({ file, settings }); }} />
    </aside>
    <section className="flex min-w-0 flex-col gap-4" aria-label="Résultat de la broderie">
      {capabilities.isError && <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Moteur indisponible</Alert.Title><Alert.Description>{capabilities.error.message}</Alert.Description><Button size="sm" variant="secondary" className="mt-2" onPress={() => { void capabilities.refetch(); }}>Réessayer</Button></Alert.Content></Alert>}
      {error && <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Traitement impossible</Alert.Title><Alert.Description>{error}</Alert.Description></Alert.Content></Alert>}
      <ResultPane file={file} sourcePreview={preview} result={generation.data} busy={generation.isPending} />
      <p role="status" aria-live="polite" className="sr-only">{generation.isPending ? "Génération en cours" : generation.isSuccess ? "Fichiers prêts" : ""}</p>
    </section>
  </div>;
}
