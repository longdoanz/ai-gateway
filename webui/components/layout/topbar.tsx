"use client";

import { useState, useRef, useEffect } from "react";
import { usePathname } from "next/navigation";
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
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showMenu) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showMenu]);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/30 bg-white/70 backdrop-blur-2xl shadow-[0_1px_0_rgba(0,0,0,0.04),0_4px_16px_rgba(31,38,135,0.05)] flex justify-between items-center px-8 h-14 tracking-tight">
      <div className="flex items-center gap-8 h-full">
        <h2 className="text-base font-semibold text-on-surface">{title}</h2>
      </div>
      <div className="flex items-center gap-3">
        <div className="relative hidden lg:block">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/60 text-sm">search</span>
          <input
            type="text"
            placeholder="Search..."
            className="w-56 pl-9 pr-4 py-1.5 bg-white/60 border border-outline-variant/50 rounded-full text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container/50 focus:bg-white/90 transition-all"
          />
        </div>
        <div className="flex items-center gap-1 border-l border-outline-variant/20 pl-3 ml-1">
          <button className="p-1.5 text-on-surface-variant/70 hover:text-primary-container hover:bg-surface-container rounded-full transition-colors relative">
            <span className="material-symbols-outlined text-[20px]">notifications</span>
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-error rounded-full" />
          </button>
          <div className="relative ml-1" ref={menuRef}>
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="flex items-center gap-2 hover:bg-surface-container px-2 py-1 rounded-full text-on-surface-variant transition-colors"
            >
              <div className="w-7 h-7 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
                {user ? (user.username || user.role).slice(0, 2).toUpperCase() : "?"}
              </div>
              {user && <span className="hidden lg:block text-sm font-medium text-on-surface">{user.username || user.role}</span>}
              <span className="material-symbols-outlined text-[16px] text-on-surface-variant/60">expand_more</span>
            </button>
            {showMenu && (
              <div className="absolute right-0 top-full mt-2 w-44 bg-white/90 backdrop-blur-xl rounded-xl shadow-[0_8px_24px_rgba(0,0,0,0.08)] border border-white/80 py-1 z-50">
                <div className="px-4 py-2 border-b border-outline-variant/20">
                  <p className="text-xs font-medium text-on-surface">{user?.username}</p>
                  <p className="text-xs text-on-surface-variant capitalize">{user?.role}</p>
                </div>
                <button
                  onClick={logout}
                  className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-error hover:bg-error/5 transition-colors"
                >
                  <span className="font-medium">Logout</span>
                  <span className="material-symbols-outlined text-base">logout</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
