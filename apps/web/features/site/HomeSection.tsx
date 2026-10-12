import type { ReactNode } from "react";
import { Reveal } from "@/features/ui/Reveal";

/** Full-width background, with the same readable content width as the hero. */
export function HomeSection({
  id,
  children,
  className = "",
}: {
  id: string;
  children: ReactNode;
  className?: string;
}) {
  return <Reveal as="section" variant="section" id={id} className={`home-section scroll-mt-24 px-4 py-8 sm:px-6 sm:py-12 ${className}`}>
    <div className="mx-auto w-full max-w-7xl">{children}</div>
  </Reveal>;
}
