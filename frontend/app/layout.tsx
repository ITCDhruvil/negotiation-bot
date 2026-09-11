import type { Metadata } from "next";
import { Figtree, IBM_Plex_Mono, Syne } from "next/font/google";

import "./globals.css";

const syne = Syne({ subsets: ["latin"], variable: "--font-syne", display: "swap" });
const figtree = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
const plex = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Aria · SKODA sourcing",
  description: "Negotiate parts pricing with Aria, SKODA's procurement assistant.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${syne.variable} ${figtree.variable} ${plex.variable} font-sans antialiased`}>
        {children}
      </body>
    </html>
  );
}
