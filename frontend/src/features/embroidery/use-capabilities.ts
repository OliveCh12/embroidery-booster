"use client";

import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/api";
import type { Capabilities } from "./types";

export function useCapabilities() {
  return useQuery({
    queryKey: ["capabilities"],
    queryFn: ({ signal }) => apiRequest<Capabilities>("/api/capabilities", { signal }),
  });
}
