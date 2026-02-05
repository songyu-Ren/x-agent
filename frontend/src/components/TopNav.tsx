"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/app/providers";

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      className={[
        "rounded-md px-3 py-2 text-sm font-medium",
        active ? "bg-zinc-900 text-white" : "text-zinc-700 hover:bg-zinc-200",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function TopNav() {
  const { user, logout } = useAuth();
  const router = useRouter();

  return (
    <div className="border-b bg-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
        <div className="flex items-center gap-2">
          <div className="text-sm font-semibold text-zinc-900">Approval Console</div>
          <div className="ml-4 flex items-center gap-1">
            <NavLink href="/" label="Drafts" />
            <NavLink href="/runs" label="Runs" />
            <NavLink href="/settings" label="Settings" />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-sm text-zinc-600">{user?.username}</div>
          <button
            className="rounded-md border px-3 py-2 text-sm hover:bg-zinc-50"
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
            type="button"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  );
}

