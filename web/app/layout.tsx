import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Corvus — Follow the evidence", template: "%s · Corvus" },
  description:
    "An independent SOC workspace connecting Wazuh alerts to evidence-backed investigation.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
