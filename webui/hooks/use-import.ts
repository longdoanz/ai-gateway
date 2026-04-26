import { useMutation } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { ImportResult } from "@/lib/types";

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
