import localFont from "next/font/local";

export const homeFont = localFont({
  src: "./fonts/manrope-latin.woff2",
  weight: "400 800",
  display: "swap",
  variable: "--font-home",
});
