export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, options);
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError("Le moteur est inaccessible. Vérifiez que le serveur Python est lancé.", 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body && typeof body === "object" && "error" in body && typeof body.error === "string"
      ? body.error
      : response.status === 413
        ? "Le fichier dépasse la limite de 10 Mio."
        : "Le moteur ne répond pas. Réessayez dans quelques instants.";
    throw new ApiError(message, response.status);
  }
  if (!body || typeof body !== "object") throw new ApiError("Réponse inattendue du moteur.", response.status);
  return body as T;
}
