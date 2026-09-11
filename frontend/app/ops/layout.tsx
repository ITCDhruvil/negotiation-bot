import type { Metadata } from "next";

import { OpsShell } from "@/components/OpsShell";

export const metadata: Metadata = {
  title: "Aria · ops",
  description: "SKODA-side status, data, logs, and fine-tune controls.",
};

export default function OpsLayout({ children }: { children: React.ReactNode }) {
  return <OpsShell>{children}</OpsShell>;
}
