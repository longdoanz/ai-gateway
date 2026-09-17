import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import apiClient from "@/lib/api-client";
import type {
  ServiceAccountCreate,
  ServiceAccountKeyCreated,
  ServiceAccountKeyResponse,
  ServiceAccountResponse,
  ServiceAccountUpdate,
  ServiceAccountUsageHistoryResponse,
} from "@/lib/types";

export function useServiceAccounts() {
  return useQuery({
    queryKey: ["service-accounts"],
    queryFn: async () => {
      const res = await apiClient.get<ServiceAccountResponse[]>("/service-accounts");
      return res.data;
    },
  });
}

export function useCreateServiceAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: ServiceAccountCreate) => {
      const res = await apiClient.post<ServiceAccountResponse>("/service-accounts", data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["service-accounts"] }),
  });
}

export function useUpdateServiceAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: number; data: ServiceAccountUpdate }) => {
      const res = await apiClient.patch<ServiceAccountResponse>(`/service-accounts/${id}`, data);
      return res.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["service-accounts"] }),
  });
}

export function useDeleteServiceAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await apiClient.delete(`/service-accounts/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["service-accounts"] }),
  });
}

export function useServiceAccountKeys(serviceAccountId: number | null) {
  return useQuery({
    queryKey: ["service-accounts", serviceAccountId, "keys"],
    queryFn: async () => {
      const res = await apiClient.get<ServiceAccountKeyResponse[]>(`/service-accounts/${serviceAccountId}/keys`);
      return res.data;
    },
    enabled: serviceAccountId !== null,
  });
}

export function useCreateServiceAccountKey(serviceAccountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await apiClient.post<ServiceAccountKeyCreated>(`/service-accounts/${serviceAccountId}/keys`);
      return res.data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["service-accounts", serviceAccountId, "keys"] });
      qc.invalidateQueries({ queryKey: ["service-accounts"] });
    },
  });
}

export function useRevokeServiceAccountKey(serviceAccountId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (keyId: number) => {
      await apiClient.delete(`/service-accounts/${serviceAccountId}/keys/${keyId}`);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["service-accounts", serviceAccountId, "keys"] });
      qc.invalidateQueries({ queryKey: ["service-accounts"] });
    },
  });
}

export function useServiceAccountUsage(serviceAccountId: number | null, days = 30) {
  return useQuery({
    queryKey: ["service-accounts", serviceAccountId, "usage", days],
    queryFn: async () => {
      const res = await apiClient.get<ServiceAccountUsageHistoryResponse>(
        `/service-accounts/${serviceAccountId}/usage`,
        { params: { days } }
      );
      return res.data;
    },
    enabled: serviceAccountId !== null,
  });
}
