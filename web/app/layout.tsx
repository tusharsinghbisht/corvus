import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const inter = localFont({
  src: "../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  variable: "--font-body",
  weight: "100 900",
  display: "swap",
});

const bricolage = localFont({
  src: "../node_modules/@fontsource-variable/bricolage-grotesque/files/bricolage-grotesque-latin-wght-normal.woff2",
  variable: "--font-heading",
  weight: "200 800",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Corvus — Follow the evidence", template: "%s · Corvus" },
  description:
    "An independent SOC workspace connecting Wazuh alerts to evidence-backed investigation.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${inter.variable} ${bricolage.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
