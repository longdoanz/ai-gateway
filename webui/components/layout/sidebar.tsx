"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Users, Upload, UserCog, Settings, LogOut } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard, adminOnly: false },
  { href: "/users", label: "Directory", icon: Users, adminOnly: false },
  { href: "/import", label: "Import", icon: Upload, adminOnly: true },
  { href: "/accounts", label: "Accounts", icon: UserCog, adminOnly: true },
  { href: "/settings", label: "Settings", icon: Settings, adminOnly: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || user?.role === "admin"
  );

  return (
    <nav className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-64 border-r border-white/60 bg-white/40 backdrop-blur-2xl shadow-[4px_0_24px_rgba(0,0,0,0.02)] z-40">
      <div className="p-6">
        <h1 className="text-xl font-bold tracking-tight text-primary">Glacier AI</h1>
        <p className="text-xs text-on-surface-variant mt-1 font-medium">Credit Manager</p>
      </div>

      <div className="flex-1 px-4 space-y-1">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-3 rounded-xl transition-colors duration-200 font-medium",
                isActive
                  ? "text-primary bg-white/80 shadow-sm border border-white"
                  : "text-on-surface-variant hover:bg-white/60 hover:text-primary"
              )}
            >
              <item.icon className="w-5 h-5" />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </div>

      <div className="p-4 mt-auto border-t border-white/60">
        <button
          onClick={logout}
          className="flex items-center gap-3 px-4 py-3 w-full rounded-xl text-on-surface-variant hover:bg-white/60 hover:text-error transition-colors font-medium"
        >
          <LogOut className="w-5 h-5" />
          <span>Logout</span>
        </button>
        {user && (
          <div className="mt-3 px-4 flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs border border-primary/20">
              {user.role === "admin" ? "A" : "U"}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-on-surface truncate capitalize">{user.role} User</p>
              <p className="text-xs text-on-surface-variant truncate">ID: {user.id}</p>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}
