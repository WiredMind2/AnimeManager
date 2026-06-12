import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Offline — AnimeManager",
};

export default function OfflineLayout({ children }: { children: React.ReactNode }) {
  return children;
}
