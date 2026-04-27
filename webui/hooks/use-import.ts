import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ImportResult } from "@/lib/types";

export interface KiroUserResponse {
  kiro_user_id: string;
  email?: string;
  username?: string;
  imported_at?: string;
  is_active: boolean;
}

export function useKiroUsers(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["kiro-users", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<KiroUserResponse[]>("/import/kiro-users", {
        params: { limit, offset },
      });
      return res.data;
    },
  });
}

export function useToggleKiroUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ kiroUserId, isActive }: { kiroUserId: string; isActive: boolean }) => {
      const res = await apiClient.patch<KiroUserResponse>(
        `/import/kiro-users/${encodeURIComponent(kiroUserId)}`,
        { is_active: isActive },
      );
      return res.data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["kiro-users"] }),
  });
}

export function useImportUsers() {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const res = await apiClient.post<ImportResult>("/import/users", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return res.data;
    },
  });
}
