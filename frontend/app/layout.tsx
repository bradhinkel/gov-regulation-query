import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Federal Regulation Query",
  description: "Plain English and legal analysis of federal regulations via eCFR",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
