import type { Metadata } from "next";
import localFont from "next/font/local";
import { PresenterBar } from "@/components/presenter-bar";
import "./globals.css";

// Self-hosted (OFL licensed, see src/app/fonts/) so builds and demos never depend on Google Fonts.
const publicSans = localFont({ src: "./fonts/public-sans-latin-wght-normal.woff2", weight: "100 900", variable: "--font-public-sans" });
const plexMono = localFont({ src: "./fonts/ibm-plex-mono-latin-400-normal.woff2", weight: "400", variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: { default: "Sentinel", template: "%s · Sentinel" },
  description: "Sentinel watches a team of AI agents and recommends containment to a human.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${publicSans.variable} ${plexMono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <PresenterBar />
        {children}
      </body>
    </html>
  );
}
