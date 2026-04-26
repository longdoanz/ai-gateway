"use client";

import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const pageTitles: Record<string, string> = {
  "/": "System Overview",
  "/users": "User & Tokens",
  "/import": "Import Mappings",
  "/accounts": "Account Management",
  "/settings": "Gateway Configuration",
};

export function Topbar() {
  const pathname = usePathname();
  const { user } = useAuth();
  const title = pageTitles[pathname] || "Dashboard";

  return (
    <header className="sticky top-0 z-30 w-full border-b border-white/20 bg-white/60 backdrop-blur-2xl shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] flex justify-between items-center px-8 h-16">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-bold text-on-surface">{title}</h2>
      </div>
      <div className="flex items-center gap-4">
        <button className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-full transition-colors relative">
          <Bell className="w-5 h-5" />
        </button>
        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs border border-primary/20">
          {user?.role === "admin" ? "A" : "U"}
        </div>
      </div>
    </header>
  );
}
