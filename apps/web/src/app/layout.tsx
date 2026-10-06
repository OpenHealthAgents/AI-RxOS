import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "../components/Providers";

export const metadata: Metadata = {
  title: "NeoZenome — AI-Powered Oncology Asset Intelligence",
  description: "Evidence-grounded drug opportunity discovery engine for biopharma decision intelligence.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="overflow-hidden bg-[#f8fafc]">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
