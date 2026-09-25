import Image from "next/image";

const SYMBOL = "/icones/beauty-salon-symbol.png";
const WORDMARK = "/icones/beauty-salon-wordmark.png";
const LOCKUP = "/icones/beauty-salon-bs-monogram-logo.png";

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

/** Complete mark for spacious placements, such as the platform footer. */
export function BeautySalonLockup() {
  return (
    <span className="relative inline-block h-12 w-[250px] overflow-hidden sm:w-[270px]" role="img" aria-label="Beauty Salon">
      <Image
        src={LOCKUP}
        alt=""
        width={2172}
        height={724}
        className="platform-logo-footer absolute left-1/2 top-1/2 !h-auto !w-[285px] max-w-none -translate-x-1/2 -translate-y-1/2 sm:!w-[310px]"
      />
    </span>
  );
}

/** Wordmark alone leaves the mobile footer compact without losing the brand name. */
export function BeautySalonFooterWordmark() {
  return (
    <span className="relative inline-block h-10 w-48 overflow-hidden" role="img" aria-label="Beauty Salon">
      <Image
        src={WORDMARK}
        alt=""
        width={2172}
        height={724}
        className="platform-logo-footer absolute left-1/2 top-1/2 !h-auto !w-[215px] max-w-none -translate-x-1/2 -translate-y-1/2"
      />
    </span>
  );
}
