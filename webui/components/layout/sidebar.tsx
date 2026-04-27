"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, BarChart3, UserCog, Settings, LogOut, ChevronUp } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, adminOnly: false },
  { href: "/analytics", label: "Analytics", icon: BarChart3, adminOnly: false },
  { href: "/accounts", label: "Accounts", icon: UserCog, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
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

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || user?.role === "admin"
  );

  return (
    <nav className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-64 border-r border-slate-200/50 bg-white/60 backdrop-blur-xl shadow-[0_0_30px_rgba(0,0,0,0.02)] z-40">
      <div className="p-6 mb-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary-container to-primary flex items-center justify-center text-white font-bold shadow-sm">
            AI
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-on-surface">AI Gateway</h1>
            <p className="text-xs text-on-surface-variant font-medium">AI Usage Management</p>
          </div>
        </div>
      </div>

      <div className="flex-1 px-4 space-y-1">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 font-medium",
                isActive
                  ? "text-primary bg-primary/5 shadow-sm border border-primary/10 font-semibold"
                  : "text-on-surface-variant hover:bg-white/60 hover:text-primary hover:-translate-y-[1px] active:scale-95"
              )}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="p-4 mt-auto space-y-1 border-t border-slate-200/50 relative">
        {user && (
          <div className="relative" ref={menuRef}>
            {showMenu && (
              <div className="absolute bottom-full mb-2 w-full bg-white rounded-xl shadow-lg border border-outline-variant/30 py-1 z-50">
                <button
                  onClick={logout}
                  className="flex items-center justify-between w-full px-4 py-2.5 text-sm text-error hover:bg-error/5 transition-colors"
                >
                  <span className="font-medium">Logout</span>
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            )}
            <button
              onClick={() => setShowMenu(!showMenu)}
              className="flex items-center gap-3 w-full p-2 rounded-xl hover:bg-surface-container-low transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30 ring-2 ring-surface-container">
                {(user.username || user.role).slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-on-surface truncate">{user.username || (user.role === "admin" ? "Admin" : "User")}</p>
                <p className="text-xs text-on-surface-variant truncate capitalize">{user.role}</p>
              </div>
              <ChevronUp
                className={cn("w-4 h-4 text-on-surface-variant transition-transform", showMenu && "rotate-180")}
              />
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
