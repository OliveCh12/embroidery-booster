"use client";

import { Alert, Button } from "@heroui/react";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, apiRequest } from "@/lib/api";
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
    const error = selected ? validateFile(selected) : null;
    setFileError(error);
    if (error) return;
    generation.reset();
    setFile(selected);
    setPreview(selected && /\.(svg|png|jpe?g|webp|bmp|gif)$/i.test(selected.name) ? URL.createObjectURL(selected) : null);
  }

  const error = generation.error?.message;
  return <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-[300px_minmax(0,1fr)] lg:grid-cols-[320px_minmax(0,1fr)]">
    <section className="flex min-h-0 min-w-0 flex-col gap-4 md:col-start-2 md:row-start-1" aria-label="Résultat de la broderie">
      {capabilities.isError && <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Moteur indisponible</Alert.Title><Alert.Description>{capabilities.error.message}</Alert.Description><Button size="sm" variant="secondary" className="mt-2" onPress={() => { void capabilities.refetch(); }}>Réessayer</Button></Alert.Content></Alert>}
      {error && <Alert status="danger"><Alert.Indicator /><Alert.Content><Alert.Title>Traitement impossible</Alert.Title><Alert.Description>{error}</Alert.Description></Alert.Content></Alert>}
      <ResultPane file={file} sourcePreview={preview} result={generation.data} busy={generation.isPending}
        importError={fileError} onSelect={selectFile} onClear={() => selectFile(null)} />
      <p role="status" aria-live="polite" className="sr-only">{generation.isPending ? "Génération en cours" : generation.isSuccess ? "Fichiers prêts" : file ? `Dessin chargé : ${file.name}` : ""}</p>
    </section>
    <aside className="flex min-h-0 min-w-0 flex-col gap-4 md:col-start-1 md:row-start-1" aria-label="Préparation de la broderie">
      <SettingsForm settings={settings} onChange={setSettings} capabilities={capabilities.data}
        busy={generation.isPending} canGenerate={!!file && !!capabilities.data && !capabilities.isError}
        onSubmit={() => { if (file) generation.mutate({ file, settings }); }} />
    </aside>
  </div>;
}
