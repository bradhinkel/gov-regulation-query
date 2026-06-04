import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

// Three typefaces (per the redesign), self-hosted from app/fonts/ so the build
// needs no network. Spectral (display + prose), Public Sans (UI), IBM Plex Mono
// (citation refs / meta). Each exposes a CSS variable consumed by globals.css.
const spectral = localFont({
  variable: "--font-spectral",
  display: "swap",
  src: [
    { path: "./fonts/spectral-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/spectral-500-normal.woff2", weight: "500", style: "normal" },
    { path: "./fonts/spectral-600-normal.woff2", weight: "600", style: "normal" },
    { path: "./fonts/spectral-700-normal.woff2", weight: "700", style: "normal" },
    { path: "./fonts/spectral-400-italic.woff2", weight: "400", style: "italic" },
    { path: "./fonts/spectral-500-italic.woff2", weight: "500", style: "italic" },
  ],
});

const publicSans = localFont({
  variable: "--font-public-sans",
  display: "swap",
  src: [
    { path: "./fonts/public-sans-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/public-sans-500-normal.woff2", weight: "500", style: "normal" },
    { path: "./fonts/public-sans-600-normal.woff2", weight: "600", style: "normal" },
    { path: "./fonts/public-sans-700-normal.woff2", weight: "700", style: "normal" },
  ],
});

const plexMono = localFont({
  variable: "--font-plex-mono",
  display: "swap",
  src: [
    { path: "./fonts/ibm-plex-mono-400-normal.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-500-normal.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-mono-600-normal.woff2", weight: "600", style: "normal" },
  ],
});

export const metadata: Metadata = {
  title: "Federal Regulation Query",
  description:
    "Plain English and legal analysis of federal regulations, grounded in the current eCFR.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      data-theme="dark"
      className={`${spectral.variable} ${publicSans.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
