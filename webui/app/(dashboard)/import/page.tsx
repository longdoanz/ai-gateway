"use client";

import { useCallback, useState } from "react";
import { Upload, FileText, AlertCircle, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useImportUsers } from "@/hooks/use-import";
import type { ImportResult } from "@/lib/types";

interface PreviewRow {
  kiro_user_id: string;
  email?: string;
  username?: string;
  error?: string;
}

function parseCSV(text: string): PreviewRow[] {
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
    return {
      kiro_user_id: cols[idIdx],
      email: emailIdx >= 0 ? cols[emailIdx] : undefined,
      username: usernameIdx >= 0 ? cols[usernameIdx] : undefined,
    };
  });
}

function parseJSON(text: string): PreviewRow[] {
  try {
    const data = JSON.parse(text);
    if (!Array.isArray(data)) return [{ kiro_user_id: "", error: "JSON must be an array" }];
    return data.map((row: any, i: number) => {
      if (!row.kiro_user_id) {
        return { kiro_user_id: "", error: `Row ${i}: missing kiro_user_id` };
      }
      return { kiro_user_id: row.kiro_user_id, email: row.email, username: row.username };
    });
  } catch {
    return [{ kiro_user_id: "", error: "Invalid JSON" }];
  }
}

export default function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
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
      const rows = f.name.endsWith(".json") ? parseJSON(text) : parseCSV(text);
      setPreview(rows);
    };
    reader.readAsText(f);
  }, []);

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
  }

  const validRows = preview.filter((r) => !r.error);
  const errorRows = preview.filter((r) => r.error);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-h1 font-bold text-on-surface tracking-tight">Import User Mappings</h1>
        <p className="text-on-surface-variant mt-1 text-sm max-w-2xl">
          Map kiro_user_id (AWS identity) to username or email for meaningful reports. Upload a CSV or JSON file.
        </p>
      </div>

      {/* Drop Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`glass-panel rounded-2xl p-12 text-center border-2 border-dashed transition-colors ${dragOver ? "border-primary bg-primary/5" : "border-outline-variant/50"}`}
      >
        <Upload className="w-12 h-12 text-on-surface-variant mx-auto mb-4" />
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
            <FileText className="w-4 h-4" /> {file.name} ({(file.size / 1024).toFixed(1)} KB)
          </div>
        )}
      </div>

      {/* Preview Table */}
      {preview.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Badge variant="secondary">{validRows.length} valid</Badge>
              {errorRows.length > 0 && <Badge variant="destructive">{errorRows.length} errors</Badge>}
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
                      {row.error ? (
                        <span className="text-error text-xs flex items-center gap-1"><AlertCircle className="w-3 h-3" /> {row.error}</span>
                      ) : (
                        <span className="text-emerald-600 text-xs flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Valid</span>
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

      {/* Import Result */}
      {result && (
        <div className="glass-panel-elevated rounded-2xl p-6">
          <h3 className="text-lg font-semibold text-on-surface flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600" /> Import Complete
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
