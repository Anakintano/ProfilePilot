import type { ReactNode } from "react";
import { Sidebar } from "@/components/Sidebar";

// Route group layout (the "(app)" segment is not part of the URL) — wraps
// the product pages (intake, upload, analyses/*, privacy, and eventually
// scribe) with the persistent sidebar. The landing page at "/" stays
// outside this group and keeps its plain marketing-page layout.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="min-w-0 flex-1 overflow-y-auto">{children}</div>
    </div>
  );
}
