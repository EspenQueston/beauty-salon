import Image from "next/image";

const SYMBOL = "/icones/beauty-salon-symbol.png";
const WORDMARK = "/icones/beauty-salon-wordmark.png";
const WORDMARK_PIED = "/icones/beauty-salon-wordmark-pied.png";

/** The source artwork has transparent margins; these wrappers crop only those margins. */
export function BeautySalonSymbol({ className = "size-8" }: { className?: string }) {
  return (
    <span className={`relative inline-block shrink-0 overflow-hidden ${className}`} aria-hidden="true">
      <Image
        src={SYMBOL}
        alt=""
        width={1254}
        height={1254}
        // Affiché à 47 px au plus (size-10 à 118 %). Sans `sizes`, Next servait
        // l'original, jusqu'à 3 840 px et 47 ko pour une icône.
        sizes="48px"
        className="platform-logo absolute left-1/2 top-1/2 !size-[118%] max-w-none -translate-x-1/2 -translate-y-1/2 object-contain"
      />
    </span>
  );
}

export function BeautySalonBrand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="inline-flex shrink-0 items-center gap-1" role="img" aria-label="Beauty Salon">
      <BeautySalonSymbol className="size-8 sm:size-9" />
      <span className={`relative hidden h-8 overflow-hidden sm:block ${compact ? "sm:w-[133px]" : "sm:w-[145px]"}`} aria-hidden="true">
        <Image
          src={WORDMARK}
          alt=""
          width={2172}
          height={724}
          sizes="170px"
          className={`platform-logo absolute left-1/2 top-1/2 !h-auto max-w-none -translate-x-1/2 -translate-y-1/2 ${compact ? "!w-[150px]" : "!w-[166px]"}`}
        />
      </span>
    </span>
  );
}

/**
 * The wordmark of the platform footer, which is dark in both UI modes.
 *
 * `beauty-salon-wordmark-pied.png` is the same artwork, trimmed to the
 * letters and filled with rgb(237, 59, 118): exactly the colour the header
 * logo takes on screen in dark mode (the berry #AE2553 through the
 * `.platform-logo` filter, brightness 1.45 then saturate 0.9). A paler tint
 * used here before read as another brand next to the header. The original
 * berry reaches only 3.0:1 on the footer background (#0b0b10); this one 5.1:1.
 *
 * The file was renamed rather than overwritten: `/icones` is cached for a
 * week, and phones would have kept the old colour. The previous version brightened the berry with a CSS filter and
 * a blurred glow, inside a box narrower than the image — the letters looked
 * soft and the final "n" was cut off.
 *
 * Displayed at its true ratio (1200 × 228), with no crop and no filter: Next
 * serves 1× and 2× versions of the fixed width, sharp on high-density screens.
 */
export function BeautySalonFooterWordmark() {
  return (
    <Image
      src={WORDMARK_PIED}
      alt="Beauty Salon"
      width={1200}
      height={228}
      sizes="(min-width: 640px) 220px, 176px"
      className="h-auto w-44 select-none sm:w-[220px]"
      draggable={false}
    />
  );
}
