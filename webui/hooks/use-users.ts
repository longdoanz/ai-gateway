import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type { UserCreate, UserDetailResponse, UserResponse, UserUpdate } from "@/lib/types";

export function useUsers(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["users", limit, offset],
    queryFn: async () => {
      const res = await apiClient.get<UserResponse[]>("/users", { params: { limit, offset } });
      return res.data;
    },
  });
}

export function useUserDetail(userId: number | null) {
  return useQuery({
    queryKey: ["users", userId],
    queryFn: async () => {
      const res = await apiClient.get<UserDetailResponse>(`/users/${userId}`);
      return res.data;
    },
    enabled: userId !== null,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: UserCreate) => {
      const res = await apiClient.post<UserResponse>("/users", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, data }: { userId: number; data: UserUpdate }) => {
      const res = await apiClient.put<UserResponse>(`/users/${userId}`, data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useProvisionUserByEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (email: string) => {
      const res = await apiClient.post<UserResponse>("/users/provision-by-email", { email });
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

