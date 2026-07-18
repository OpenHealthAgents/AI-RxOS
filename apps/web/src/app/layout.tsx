import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-RxOS",
  description: "AI-native drug discovery operating system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
