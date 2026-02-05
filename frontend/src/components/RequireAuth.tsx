"use client";

import { PropsWithChildren, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/app/providers";

export function RequireAuth({ children }: PropsWithChildren) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user && pathname !== "/login") {
      router.replace("/login");
    }
  }, [loading, pathname, router, user]);

  if (loading) {
    return (
      <div className="min-h-screen bg-zinc-50">
        <div className="mx-auto max-w-5xl px-6 py-10">
          <div className="h-8 w-48 animate-pulse rounded bg-zinc-200" />
          <div className="mt-6 grid gap-3">
            <div className="h-20 animate-pulse rounded bg-white shadow-sm" />
            <div className="h-20 animate-pulse rounded bg-white shadow-sm" />
            <div className="h-20 animate-pulse rounded bg-white shadow-sm" />
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}

