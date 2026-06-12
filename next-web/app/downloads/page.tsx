import DownloadsDashboard from "@/components/downloads/DownloadsDashboard";
import { api } from "@/lib/api";

export const metadata = {
  title: "Downloads — AnimeManager",
};

export default async function DownloadsPage() {
  let initial;
  try {
    initial = await api.getDownloadsOverview();
  } catch {
    initial = {
      overview: {},
      counts: { active: 0, seeding: 0, completed: 0, error: 0, other: 0 },
    };
  }

  return <DownloadsDashboard initial={initial} />;
}
