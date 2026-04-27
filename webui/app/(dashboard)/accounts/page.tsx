"use client";

import { useCallback, useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useKeys, useCreateKey, useToggleKey } from "@/hooks/use-keys";
import { useUsers, useCreateUser, useUpdateUser } from "@/hooks/use-users";
import { useImportUsers, useKiroUsers } from "@/hooks/use-import";
import { useAuth } from "@/hooks/use-auth";
import { maskKey, formatCredits } from "@/lib/utils";
import type { ApiKeyResponse, UserResponse, ImportResult } from "@/lib/types";

// --- Access & Overrides components (from users page) ---

function AddKeyDialog() {
  const [rawKey, setRawKey] = useState("");
  const [open, setOpen] = useState(false);
  const createKey = useCreateKey();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await createKey.mutateAsync({ raw_key: rawKey });
    setRawKey("");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" className="gap-2 bg-primary-container text-on-primary rounded-lg shadow-[0_2px_8px_rgba(79,70,229,0.2)] hover:-translate-y-[1px] hover:bg-primary-container/95 transition-transform" />}>
        <span className="material-symbols-outlined text-[18px]">add</span> Register Key
      </DialogTrigger>
      <DialogContent className="glass-panel-elevated">
        <DialogHeader>
          <DialogTitle>Register API Key</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="raw_key">Kiro API Key</Label>
            <Input id="raw_key" value={rawKey} onChange={(e) => setRawKey(e.target.value)} placeholder="sk-proj-..." className="font-mono text-sm" required minLength={10} />
            <p className="text-xs text-on-surface-variant">The key will be encrypted. Only prefix and suffix are stored visibly.</p>
          </div>
          <Button type="submit" disabled={createKey.isPending} className="w-full">
            {createKey.isPending ? "Registering..." : "Register Key"}
          </Button>
          {createKey.isError && (
            <p className="text-sm text-error">{(createKey.error as unknown as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to register key"}</p>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKeyResponse }) {
  const toggleKey = useToggleKey();
  return (
    <tr className="border-b border-outline-variant/20">
      <td className="py-3 px-4 text-on-surface font-medium text-xs">{apiKey.kiro_user_id || "—"}</td>
      <td className="py-3 px-4 font-mono text-on-surface-variant text-xs">{maskKey(apiKey.key_prefix, apiKey.key_suffix)}</td>
      <td className="py-3 px-4 text-on-surface-variant text-xs">{new Date(apiKey.created_at).toLocaleDateString()}</td>
      <td className="py-3 px-4 text-right">
        <Switch checked={apiKey.is_active} onCheckedChange={(checked) => toggleKey.mutate({ keyId: apiKey.id, isActive: checked })} disabled={toggleKey.isPending} />
      </td>
    </tr>
  );
}

function UserRow({ user, keys, isExpanded, onToggle }: { user: UserResponse; keys: ApiKeyResponse[]; isExpanded: boolean; onToggle: () => void }) {
  const userKeys = keys.filter((k) => k.user_id === user.id);
  return (
    <>
      <tr className={`hover:bg-surface-container-lowest transition-colors cursor-pointer group ${isExpanded ? "bg-sky-50/30" : ""}`} onClick={onToggle}>
        <td className="py-4 px-6 text-center">
          <button className="text-outline group-hover:text-primary-container hover:bg-surface-container rounded-full p-0.5 transition-colors">
            {isExpanded ? <span className="material-symbols-outlined text-lg">expand_more</span> : <span className="material-symbols-outlined text-lg">chevron_right</span>}
          </button>
        </td>
        <td className="py-4 px-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center text-on-surface-variant font-semibold text-xs border border-outline-variant/30">{user.username.slice(0, 2).toUpperCase()}</div>
            <div><div className="font-medium text-on-surface">{user.username}</div></div>
          </div>
        </td>
        <td className="py-4 px-6"><Badge variant={user.role === "admin" ? "default" : "secondary"} className="text-[10px]">{user.role}</Badge></td>
        <td className="py-4 px-6">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${user.is_active ? "bg-emerald-100/50 text-emerald-800 border-emerald-200/50" : "bg-surface-variant text-on-surface-variant border-outline-variant/50"}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${user.is_active ? "bg-emerald-500" : "bg-outline"}`} />
            {user.is_active ? "Active" : "Inactive"}
          </span>
        </td>
        <td className="py-4 px-6 text-right font-mono text-sm">{userKeys.length}</td>
      </tr>
      {isExpanded && (
        <tr className="bg-surface-container-lowest border-b-2 border-primary/10">
          <td colSpan={5} className="p-0">
            <div className="px-12 py-6 pl-20 bg-gradient-to-b from-sky-50/20 to-transparent">
              <div className="flex justify-between items-center mb-4">
                <h4 className="font-mono text-mono-label text-on-surface font-semibold flex items-center gap-2"><span className="material-symbols-outlined text-sm text-sky-600">key</span> API Keys ({userKeys.length})</h4>
              </div>
              {userKeys.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No API keys registered.</p>
              ) : (
                <div className="border border-outline-variant/40 rounded-lg overflow-hidden bg-white">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-surface-container-low/50">
                      <tr>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Kiro User ID</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant font-mono">Token Secret</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant">Created</th>
                        <th className="py-2 px-4 font-medium text-on-surface-variant text-right">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant/20">
                      {userKeys.map((key) => (<KeyRow key={key.id} apiKey={key} />))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// --- Kiro Users (Import) components (from import page) ---

interface PreviewRow {
  kiro_user_id: string;
  email?: string;
  username?: string;
  error?: string;
  action?: "new" | "update";
}

function parseCSV(text: string, existingUsers: { kiro_user_id: string }[] = []): PreviewRow[] {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const idIdx = headers.indexOf("kiro_user_id");
  const emailIdx = headers.indexOf("email");
  const usernameIdx = headers.indexOf("username");

  return lines.slice(1).map((line, i) => {
    const cols = line.split(",").map((c) => c.trim());
    if (idIdx === -1 || !cols[idIdx]) {
      return { kiro_user_id: "", error: `Row ${i + 1}: missing kiro_user_id` };
    }
    const kiro_user_id = cols[idIdx];
    const exists = existingUsers.some((u) => u.kiro_user_id === kiro_user_id);
    return {
      kiro_user_id,
      email: emailIdx >= 0 ? cols[emailIdx] : undefined,
      username: usernameIdx >= 0 ? cols[usernameIdx] : undefined,
      action: exists ? "update" : "new",
    };
  });
}

function parseJSON(text: string, existingUsers: { kiro_user_id: string }[] = []): PreviewRow[] {
  try {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) return [{ kiro_user_id: "", error: "JSON must be an array" }];
    return data.map((row: Record<string, string>, i: number) => {
      if (!row.kiro_user_id) {
        return { kiro_user_id: "", error: `Row ${i}: missing kiro_user_id` };
      }
      const exists = existingUsers.some((u) => u.kiro_user_id === row.kiro_user_id);
      return { 
        kiro_user_id: row.kiro_user_id, 
        email: row.email, 
        username: row.username,
        action: exists ? "update" : "new",
      };
    });
  } catch {
    return [{ kiro_user_id: "", error: "Invalid JSON" }];
  }
}

function ImportUsersPanel({ onImportSuccess, initialFile, existingUsers = [] }: { onImportSuccess?: () => void; initialFile?: File | null; existingUsers?: { kiro_user_id: string }[] }) {
  const [file, setFile] = useState<File | null>(initialFile || null);
  const [preview, setPreview] = useState<PreviewRow[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const importUsers = useImportUsers();

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setResult(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const rows = f.name.endsWith(".json") ? parseJSON(text, existingUsers) : parseCSV(text, existingUsers);
      setPreview(rows);
    };
    reader.readAsText(f);
  }, [existingUsers]);


  
  useEffect(() => {
    if (initialFile && !file) {
      setTimeout(() => handleFile(initialFile), 0);
    }
  }, [initialFile, handleFile, file]);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  }

  async function handleImport() {
    if (!file) return;
    const res = await importUsers.mutateAsync(file);
    setResult(res);
    if (res && res.imported + res.updated > 0) {
      setTimeout(() => onImportSuccess?.(), 1500); // 1.5s delay to show success msg
    }
  }

  const validRows = preview.filter((r) => !r.error);
  const errorRows = preview.filter((r) => r.error);
  const newCount = validRows.filter((r) => r.action === "new").length;
  const updateCount = validRows.filter((r) => r.action === "update").length;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-on-surface-variant text-sm max-w-2xl">
          Map kiro_user_id (AWS identity) to username or email for meaningful reports. Upload a CSV or JSON file.
        </p>
      </div>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`glass-panel rounded-3xl p-12 text-center border-2 border-dashed transition-colors ${dragOver ? "border-primary bg-primary/5" : "border-outline-variant/50"}`}
      >
        <span className="material-symbols-outlined text-[48px] text-on-surface-variant mx-auto mb-4 block">upload</span>
        <p className="text-on-surface font-medium">Drag & drop your CSV or JSON file here</p>
        <p className="text-on-surface-variant text-sm mt-1">
          Required: <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">kiro_user_id</code>.
          Optional: <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">email</code>,{" "}
          <code className="font-mono text-xs bg-surface-container px-1 py-0.5 rounded">username</code>.
        </p>
        <label className="mt-4 inline-block">
          <input type="file" accept=".csv,.json" onChange={handleFileInput} className="hidden" />
          <span className="cursor-pointer text-sm text-primary hover:underline">or click to browse</span>
        </label>
        {file && (
          <div className="mt-4 flex items-center justify-center gap-2 text-sm text-on-surface">
            <span className="material-symbols-outlined text-[16px]">description</span> {file.name} ({(file.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

      {preview.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Badge variant="secondary">{validRows.length} valid</Badge>
              {errorRows.length > 0 && <Badge variant="destructive">{errorRows.length} errors</Badge>}
              {newCount > 0 && <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-none">{newCount} New</Badge>}
              {updateCount > 0 && <Badge variant="outline" className="bg-blue-50 text-blue-700 border-none">{updateCount} Update</Badge>}
            </div>
            <Button onClick={handleImport} disabled={validRows.length === 0 || importUsers.isPending}>
              {importUsers.isPending ? "Importing..." : `Import ${validRows.length} rows`}
            </Button>
          </div>
          <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl overflow-hidden">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-container-low/50 border-b border-outline-variant/30">
                <tr>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">#</th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Kiro User ID</th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Email</th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Username</th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Action</th>
                  <th className="py-2 px-4 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/20">
                {preview.slice(0, 50).map((row, i) => (
                  <tr key={i} className={row.error ? "bg-error/5" : ""}>
                    <td className="py-2 px-4 text-on-surface-variant text-xs">{i + 1}</td>
                    <td className="py-2 px-4 font-mono text-xs">{row.kiro_user_id || "—"}</td>
                    <td className="py-2 px-4 text-xs">{row.email || "—"}</td>
                    <td className="py-2 px-4 text-xs">{row.username || "—"}</td>
                    <td className="py-2 px-4">
                      {row.action === "new" ? (
                        <Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">New</Badge>
                      ) : row.action === "update" ? (
                        <Badge variant="secondary" className="bg-blue-100 text-blue-800 hover:bg-blue-100">Update</Badge>
                      ) : null}
                    </td>
                    <td className="py-2 px-4">
                      {row.error ? (
                        <span className="text-error text-xs flex items-center gap-1"><span className="material-symbols-outlined text-[12px]">error</span> {row.error}</span>
                      ) : (
                        <span className="text-emerald-600 text-xs flex items-center gap-1"><span className="material-symbols-outlined text-[12px]">check_circle</span> Valid</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {preview.length > 50 && (
              <div className="p-3 text-center text-xs text-on-surface-variant border-t border-outline-variant/30">Showing first 50 of {preview.length} rows</div>
            )}
          </div>
        </div>
      )}

      {result && (
        <div className="glass-panel-elevated rounded-3xl p-6">
          <h3 className="text-lg font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-[20px] text-emerald-600">check_circle</span> Import Complete
          </h3>
          <div className="mt-3 grid grid-cols-3 gap-4 text-sm">
            <div><span className="text-on-surface-variant">Imported:</span> <span className="font-semibold text-on-surface">{result.imported}</span></div>
            <div><span className="text-on-surface-variant">Updated:</span> <span className="font-semibold text-on-surface">{result.updated}</span></div>
            <div><span className="text-on-surface-variant">Errors:</span> <span className="font-semibold text-error">{result.errors.length}</span></div>
          </div>
          {result.errors.length > 0 && (
            <ul className="mt-3 text-xs text-error space-y-1">{result.errors.map((err, i) => (<li key={i}>{err}</li>))}</ul>
          )}
        </div>
      )}
    </div>
  );
}

// --- Account Management components (existing) ---

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
      <DialogTrigger render={<Button className="gap-2 shadow-[0_2px_8px_rgba(79,70,229,0.2)] hover:-translate-y-[1px] transition-transform rounded-lg" />}>
        <span className="material-symbols-outlined text-[16px]">add</span> Create Account
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
            <p className="text-sm text-error">{(createUser.error as unknown as { response?: { data?: { detail?: string } } })?.response?.data?.detail || "Failed to create account"}</p>
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
      <DialogTrigger render={<Button variant="outline" size="sm" className="hover:-translate-y-[1px] transition-transform" />}>
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

function KiroUsersWrapper() {
  const { data: kiroUsers, isLoading, refetch } = useKiroUsers();
  const [isEditing, setIsEditing] = useState(false);
  const [initialFile, setInitialFile] = useState<File | null>(null);

  if (isLoading) return <div className="space-y-3">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-16 rounded-xl" />))}</div>;

  const hasData = kiroUsers && kiroUsers.length > 0;

  if (!hasData || isEditing) {
    return (
      <div className="space-y-4">
        {hasData && (
          <div className="flex justify-between items-center bg-sky-50/50 p-4 rounded-xl border border-sky-100">
            <div>
              <h3 className="font-semibold text-on-surface">Update Imported Users</h3>
              <p className="text-sm text-on-surface-variant">Upload a new CSV/JSON to append or update users.</p>
            </div>
            <Button variant="outline" onClick={() => { setIsEditing(false); setInitialFile(null); }}>Cancel Edit</Button>
          </div>
        )}
        <ImportUsersPanel 
          onImportSuccess={() => { refetch(); setIsEditing(false); setInitialFile(null); }} 
          initialFile={initialFile}
          existingUsers={kiroUsers || []}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-lg font-semibold text-on-surface">Imported Kiro Users</h3>
          <p className="text-sm text-on-surface-variant">Manage your imported Amazon Q/Kiro users mapping.</p>
        </div>
        <label className="cursor-pointer">
          <input 
            type="file" 
            accept=".csv,.json" 
            className="hidden" 
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setInitialFile(f);
                setIsEditing(true);
                e.target.value = "";
              }
            }} 
          />
          <div className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary-container shadow-[0_2px_8px_rgba(79,70,229,0.2)] hover:-translate-y-[1px] text-on-primary h-10 px-4 py-2">
            <span className="material-symbols-outlined text-[16px]">upload</span> Edit Import
          </div>
        </label>
      </div>

      <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
              <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Kiro User ID</th>
              <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Email</th>
              <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Username</th>
            </tr>
          </thead>
          <tbody className="text-body-sm divide-y divide-outline-variant/20">
            {kiroUsers.map((user) => (
              <tr key={user.kiro_user_id} className="hover:bg-surface-container-lowest transition-colors">
                <td className="py-4 px-6 font-mono text-xs">{user.kiro_user_id}</td>
                <td className="py-4 px-6">{user.email || "—"}</td>
                <td className="py-4 px-6">{user.username || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// --- Main Page ---

export default function AccountsPage() {
  const { user: authUser } = useAuth();
  const { data: users, isLoading: usersLoading } = useUsers();
  const { data: keys, isLoading: keysLoading } = useKeys();
  const [expandedUserId, setExpandedUserId] = useState<number | null>(null);
  const [userQuery, setUserQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");
  const isLoading = usersLoading || keysLoading;

  const totalUsers = users?.length ?? 0;
  const activeTokens = keys?.filter((k) => k.is_active).length ?? 0;
  const activeProjects = new Set(keys?.filter((k) => k.is_active).map((k) => k.user_id) ?? []).size;
  const filteredUsers = (users || []).filter((u) => {
    const matchesQuery = u.username.toLowerCase().includes(userQuery.toLowerCase().trim());
    const matchesStatus = statusFilter === "all" || (statusFilter === "active" ? u.is_active : !u.is_active);
    return matchesQuery && matchesStatus;
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-h1 font-bold text-on-surface tracking-tight">Account Management</h1>
          <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">Manage users, access, API keys, and dashboard accounts.</p>
        </div>
      </div>

      <Tabs defaultValue="access" className="w-full">
        <TabsList variant="line" className="w-full justify-start h-full gap-6 rounded-none border-b border-outline-variant/30 p-0">
          <TabsTrigger
            value="access"
            className="!h-auto !rounded-none !border-0 !bg-transparent !px-0 !py-0 mt-4 pb-4 pt-4 text-slate-500 hover:text-indigo-500 transition-colors duration-200 data-[active]:text-indigo-600 data-[active]:font-bold data-[active]:border-b-2 data-[active]:border-indigo-600"
          >
            User &amp; Tokens
          </TabsTrigger>
          <TabsTrigger
            value="import"
            className="!h-auto !rounded-none !border-0 !bg-transparent !px-0 !py-0 mt-4 pb-4 pt-4 text-slate-500 hover:text-indigo-500 transition-colors duration-200 data-[active]:text-indigo-600 data-[active]:font-bold data-[active]:border-b-2 data-[active]:border-indigo-600"
          >
            Kiro Users
          </TabsTrigger>
          <TabsTrigger
            value="accounts"
            className="!h-auto !rounded-none !border-0 !bg-transparent !px-0 !py-0 mt-4 pb-4 pt-4 text-slate-500 hover:text-indigo-500 transition-colors duration-200 data-[active]:text-indigo-600 data-[active]:font-bold data-[active]:border-b-2 data-[active]:border-indigo-600"
          >
            Account Management
          </TabsTrigger>
        </TabsList>

        <TabsContent value="access" className="mt-6 space-y-6">
          <div className="flex items-center justify-end gap-3">
            <Button
              variant="outline"
              className="px-4 py-2 bg-surface-bright border border-outline-variant text-on-surface rounded-lg font-mono-label text-mono-label shadow-[0_2px_4px_rgba(0,0,0,0.02)] hover:-translate-y-[1px] transition-transform flex items-center gap-2"
              type="button"
            >
              <span className="material-symbols-outlined text-[16px]">download</span>
              Export CSV
            </Button>
            <AddKeyDialog />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-bento-gap">
            <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
              <div className="flex justify-between items-start mb-2">
                <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Total Users</span>
                <span className="material-symbols-outlined text-outline text-xl">group</span>
              </div>
              <div className="text-4xl font-display text-on-surface tracking-tight font-mono">{totalUsers}</div>
              <div className="text-xs text-on-surface-variant mt-1">registered accounts</div>
            </div>
            <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] relative overflow-hidden backdrop-blur-[20px] bg-white/80">
              <div className="absolute top-0 right-0 w-32 h-32 bg-sky-100 rounded-full blur-3xl opacity-50 -mr-10 -mt-10 pointer-events-none" />
              <div className="flex justify-between items-start mb-2 relative z-10">
                <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Active Tokens</span>
                <span className="material-symbols-outlined text-sky-600 text-xl">key</span>
              </div>
              <div className="text-4xl font-display text-on-surface tracking-tight font-mono relative z-10">{activeTokens}</div>
              <div className="text-xs text-on-surface-variant mt-1 relative z-10">Across {activeProjects} active users</div>
            </div>
            <div className="bg-surface-lowest border border-black/5 rounded-xl p-5 shadow-[0_2px_4px_rgba(0,0,0,0.04)] backdrop-blur-[20px] bg-white/80">
              <div className="flex justify-between items-start mb-2">
                <span className="text-label-caps font-label-caps text-on-surface-variant uppercase tracking-wider">Avg Keys / User</span>
                <span className="material-symbols-outlined text-outline text-xl">data_usage</span>
              </div>
              <div className="text-4xl font-display text-on-surface tracking-tight font-mono">{totalUsers > 0 ? (activeTokens / totalUsers).toFixed(1) : "0"}</div>
              <div className="text-xs text-on-surface-variant mt-1">keys per user</div>
            </div>
          </div>
          {isLoading ? (
            <div className="space-y-3">{[1, 2, 3].map((i) => (<Skeleton key={i} className="h-16 rounded-xl" />))}</div>
          ) : (
            <div className="bg-white/80 backdrop-blur-[20px] border border-black/5 rounded-xl shadow-[0_2px_8px_rgba(0,0,0,0.04)] overflow-hidden">
              <div className="p-4 border-b border-outline-variant/30 flex flex-col gap-3 md:flex-row md:justify-between md:items-center bg-surface-lowest/50">
                <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 w-full md:w-auto">
                  <div className="relative w-full sm:w-auto">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-sm">search</span>
                    <Input
                      value={userQuery}
                      onChange={(e) => setUserQuery(e.target.value)}
                      placeholder="Filter users..."
                      className="pl-9 pr-4 py-1.5 bg-surface-bright border border-outline-variant rounded-md text-sm focus:ring-2 focus:ring-primary-container/20 focus:border-primary-container transition-all w-full sm:w-64 shadow-sm"
                    />
                  </div>
                  <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as "all" | "active" | "inactive")}>
                    <SelectTrigger className="w-full sm:w-36 px-3 py-1.5 bg-surface-bright border border-outline-variant text-on-surface rounded-md font-mono-label text-mono-label flex items-center gap-2 hover:bg-surface-container transition-colors">
                      <span className="material-symbols-outlined text-sm text-on-surface-variant">filter_list</span>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Status: All</SelectItem>
                      <SelectItem value="active">Status: Active</SelectItem>
                      <SelectItem value="inactive">Status: Inactive</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="text-xs text-on-surface-variant font-medium">
                  Showing {filteredUsers.length} of {totalUsers} users
                </div>
              </div>
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-surface-container-low/50 border-b border-outline-variant/30">
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider w-12" />
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">User Details</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Role</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Status</th>
                    <th className="py-3 px-6 font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider text-right">Keys</th>
                  </tr>
                </thead>
                <tbody className="text-body-sm divide-y divide-outline-variant/20">
                  {filteredUsers.map((u) => (
                    <UserRow key={u.id} user={u} keys={keys || []} isExpanded={expandedUserId === u.id} onToggle={() => setExpandedUserId(expandedUserId === u.id ? null : u.id)} />
                  ))}
                </tbody>
              </table>
              {filteredUsers.length === 0 && (<div className="p-8 text-center text-on-surface-variant">No users match current filter.</div>)}
            </div>
          )}
        </TabsContent>

        <TabsContent value="import" className="mt-6">
          <KiroUsersWrapper />
        </TabsContent>

        <TabsContent value="accounts" className="mt-6 space-y-6">
          <div className="flex justify-end">
            <CreateUserDialog />
          </div>
          {usersLoading ? (
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
        </TabsContent>
      </Tabs>
    </div>
  );
}
