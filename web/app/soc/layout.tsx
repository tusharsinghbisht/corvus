import type { Metadata } from "next";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "Workspace",
  robots: { index: false, follow: false },
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return <Shell>{children}</Shell>;
}
