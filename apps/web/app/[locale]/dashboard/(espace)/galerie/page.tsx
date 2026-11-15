import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Gallery } from "@/features/dashboard/Gallery";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pro.navigation");
  return { title: t("galerie") };
}

export default function GalleryPage() {
  return <Gallery />;
}
