"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import { Bell, Search, Wallet, LogOut, ChevronDown } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";

const pageTitles: Record<string, string> = {
  "/": "System Overview",
  "/analytics": "Usage Analytics",
  "/accounts": "Account Management",
  "/settings": "Gateway Configuration",
};

export function Topbar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const title = pageTitles[pathname] || "Dashboard";
  const [showMenu, setShowMenu] = useState(false);

  return (
    <header className="sticky top-0 z-30 w-full border-b border-white/20 bg-white/60 backdrop-blur-2xl shadow-[0_8px_32px_0_rgba(31,38,135,0.07)] flex justify-between items-center px-8 h-16">
      <div className="flex items-center gap-8 h-full">
        <h2 className="text-lg font-bold text-on-surface">{title}</h2>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative hidden lg:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-outline" />
          <input
            type="text"
            placeholder="Search resources..."
            className="w-64 pl-9 pr-4 py-1.5 bg-surface-bright border border-outline-variant rounded-full text-sm focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container transition-all shadow-sm"
          />
        </div>
        <div className="flex items-center gap-2 border-l border-outline-variant/30 pl-4 ml-2">
          <button className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-full transition-colors relative">
            <Wallet className="w-5 h-5" />
          </button>
          <button className="p-1.5 text-on-surface-variant hover:text-primary hover:bg-surface-container rounded-full transition-colors relative">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1.5 w-2 h-2 bg-error rounded-full" />
          </button>
          <div className="relative ml-2">
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="flex items-center gap-1 hover:bg-surface-container p-1 rounded-full text-on-surface-variant transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
                {user?.role === "admin" ? "AD" : "US"}
              </div>
              <ChevronDown className="w-3 h-3 opacity-70" />
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-white rounded-xl shadow-lg border border-outline-variant/30 py-1 z-50">
                <button
                  onClick={logout}
                  className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-error hover:bg-error/5 transition-colors"
                >
                  <span className="font-medium">Logout</span>
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
