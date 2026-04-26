"use client";

import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useUsers, useCreateUser, useUpdateUser } from "@/hooks/use-users";
import type { UserResponse } from "@/lib/types";

function CreateUserDialog() {
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");
  const createUser = useCreateUser();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createUser.mutateAsync({ username, password, role });
    setUsername("");
    setPassword("");
    setRole("user");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button className="gap-2" />}>
        <Plus className="w-4 h-4" /> Create Account
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader><DialogTitle>Create Dashboard Account</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="new-username">Username</Label>
            <Input id="new-username" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Enter username" required minLength={3} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-password">Password</Label>
            <Input id="new-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" required minLength={6} />
          </div>
          <div className="space-y-2">
            <Label>Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as "admin" | "user")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="user">User</SelectItem>
                <SelectItem value="admin">Admin</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button type="submit" disabled={createUser.isPending} className="w-full">
            {createUser.isPending ? "Creating..." : "Create Account"}
          </Button>
          {createUser.isError && (
            <p className="text-sm text-error">{(createUser.error as any)?.response?.data?.detail || "Failed to create account"}</p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({ user }: { user: UserResponse }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const updateUser = useUpdateUser();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await updateUser.mutateAsync({ userId: user.id, data: { password } });
    setPassword("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        Reset Password
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader><DialogTitle>Reset Password for {user.username}</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="reset-pw">New Password</Label>
            <Input id="reset-pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter new password" required minLength={6} />
          </div>
          <Button type="submit" disabled={updateUser.isPending} className="w-full">
            {updateUser.isPending ? "Updating..." : "Update Password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ChangeRoleSelect({ user }: { user: UserResponse }) {
  const updateUser = useUpdateUser();
  return (
    <Select value={user.role} onValueChange={(newRole) => updateUser.mutate({ userId: user.id, data: { role: newRole as "admin" | "user" } })} disabled={updateUser.isPending}>
      <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
      <SelectContent>
        <SelectItem value="user">User</SelectItem>
        <SelectItem value="admin">Admin</SelectItem>
      </SelectContent>
    </Select>
  );
}

function AccountRow({ user }: { user: UserResponse }) {
  const updateUser = useUpdateUser();
  return (
    <tr className="hover:bg-surface-container-lowest transition-colors">
      <td className="py-4 px-6">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">
            {user.username.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <div className="font-medium text-on-surface">{user.username}</div>
            <div className="text-on-surface-variant text-xs mt-0.5">ID: {user.id} · Created: {new Date(user.created_at).toLocaleDateString()}</div>
          </div>
        </div>
      </td>
      <td className="py-4 px-6"><ChangeRoleSelect user={user} /></td>
      <td className="py-4 px-6">
        <Switch checked={user.is_active} onCheckedChange={(checked) => updateUser.mutate({ userId: user.id, data: { is_active: checked } })} disabled={updateUser.isPending} />
      </td>
      <td className="py-4 px-6 text-right"><ResetPasswordDialog user={user} /></td>
    </tr>
  );
}

export default function AccountsPage() {
  const { data: users, isLoading } = useUsers();
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">Account Management</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">Manage dashboard accounts. Create, deactivate, reset passwords, and assign roles.</p>
        </div>
        <CreateUserDialog />
      </div>
      {isLoading ? (
        <div className="space-y-3">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-16 rounded-xl" />))}</div>
      ) : (
        <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Account</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Role</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Active</th>
                <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="text-body-sm divide-y divide-outline-variant/20">
              {(users || []).map((u) => (<AccountRow key={u.id} user={u} />))}
            </tbody>
          </table>
          {(!users || users.length === 0) && (<div className="p-8 text-center text-on-surface-variant">No accounts found.</div>)}
        </div>
      )}
    </div>
  );
}
