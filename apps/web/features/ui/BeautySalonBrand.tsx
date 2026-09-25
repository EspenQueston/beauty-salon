import Image from "next/image";

const SYMBOL = "/icones/beauty-salon-symbol.png";
const WORDMARK = "/icones/beauty-salon-wordmark.png";
const WORDMARK_CLAIR = "/icones/beauty-salon-wordmark-clair.png";

/** The source artwork has transparent margins; these wrappers crop only those margins. */
export function BeautySalonSymbol({ className = "size-8" }: { className?: string }) {
  return (
    <span className={`relative inline-block shrink-0 overflow-hidden ${className}`} aria-hidden="true">
      <Image
        src={SYMBOL}
        alt=""
        width={1254}
        height={1254}
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
          className={`platform-logo absolute left-1/2 top-1/2 !h-auto max-w-none -translate-x-1/2 -translate-y-1/2 ${compact ? "!w-[150px]" : "!w-[166px]"}`}
        />
      </span>
    </span>
  );
}

/**
 * The wordmark of the platform footer, which is dark in both UI modes.
 *
 * `beauty-salon-wordmark-clair.png` is the same artwork, trimmed to the
 * letters and recoloured in a lighter tint of the brand hue (343°): the
 * original berry reaches only 3.0:1 on the footer background (#0b0b10), this
 * one 7.25:1. The previous version brightened the berry with a CSS filter and
 * a blurred glow, inside a box narrower than the image — the letters looked
 * soft and the final "n" was cut off.
 *
 * Displayed at its true ratio (1200 × 228), with no crop and no filter: Next
 * serves 1× and 2× versions of the fixed width, sharp on high-density screens.
 */
export function BeautySalonFooterWordmark() {
  return (
    <Image
      src={WORDMARK_CLAIR}
      alt="Beauty Salon"
      width={1200}
      height={228}
      sizes="(min-width: 640px) 220px, 176px"
      className="h-auto w-44 select-none sm:w-[220px]"
      draggable={false}
    />
  );
}
