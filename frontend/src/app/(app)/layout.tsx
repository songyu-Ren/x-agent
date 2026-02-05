import { PropsWithChildren } from "react";
import { RequireAuth } from "@/components/RequireAuth";
import { TopNav } from "@/components/TopNav";

export default function AppLayout({ children }: PropsWithChildren) {
  return (
    <RequireAuth>
      <div className="min-h-screen bg-zinc-50">
        <TopNav />
        <div className="mx-auto max-w-5xl px-6 py-8">{children}</div>
      </div>
    </RequireAuth>
  );
}

