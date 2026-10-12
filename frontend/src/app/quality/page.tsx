import type { Metadata } from "next";
import { QualityGallery } from "@/features/quality/gallery";

export const metadata: Metadata = { title: "Qualité" };

export default function Page() {
  return <QualityGallery />;
}
