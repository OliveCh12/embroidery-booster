import type { Metadata } from "next";
import { QualityGallery } from "@/features/quality/gallery";

export const metadata: Metadata = { title: "Comparaison" };

export default function Page() {
  return <QualityGallery />;
}
