"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { GoogleLogin } from "@react-oauth/google";
import { useState } from "react";

export default function LoginPage() {
  const router = useRouter();
  const { loginWithGoogle } = useAuth();
  const [error, setError] = useState("");

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--color-glacier-background)]">
      <div className="w-full max-w-sm">
        <div className="glass-panel-elevated rounded-3xl p-10 shadow-[0_8px_40px_rgba(79,70,229,0.10)]">
          <div className="text-center mb-8">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary-container to-primary flex items-center justify-center text-white font-bold text-lg shadow-[0_4px_16px_rgba(79,70,229,0.3)] mx-auto mb-4">
              AI
            </div>
            <h1 className="text-2xl font-bold text-on-surface tracking-tight">AI Gateway</h1>
            <p className="text-on-surface-variant text-sm mt-1">Sign in to your dashboard</p>
          </div>
          <div className="flex flex-col items-center gap-4">
            <GoogleLogin
              onSuccess={async (response) => {
                try {
                  setError("");
                  await loginWithGoogle(response.credential!);
                  router.push("/");
                } catch {
                  setError("Login failed. Please try again.");
                }
              }}
              onError={() => setError("Google sign-in failed. Please try again.")}
              width="320"
              theme="outline"
              size="large"
              text="signin_with"
            />
            {error && (
              <div className="flex items-center gap-2 text-sm text-error bg-error/5 border border-error/20 rounded-xl px-3 py-2 w-full">
                <span className="material-symbols-outlined text-[16px]">error</span>
                {error}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
