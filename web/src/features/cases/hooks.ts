import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import * as casesApi from './api';
import type { AuditFilters, CaseStatus } from './types';

export const caseKeys = {
  all: ['cases'] as const,
  list: (statuses?: CaseStatus[]) => ['cases', 'list', statuses?.join(',') ?? 'all'] as const,
  own: ['cases', 'own'] as const,
  detail: (id: string) => ['cases', 'detail', id] as const,
  counts: ['cases', 'counts'] as const,
};

export const useCaseList = (statuses?: CaseStatus[]) =>
  useQuery({ queryKey: caseKeys.list(statuses), queryFn: () => casesApi.listCases(statuses) });

export const useOwnCases = () => useQuery({ queryKey: caseKeys.own, queryFn: casesApi.listOwnCases });

export const useCase = (id: string | null) =>
  useQuery({ queryKey: caseKeys.detail(id ?? ''), queryFn: () => casesApi.getCase(id!), enabled: !!id });

export const useOwnCase = (id: string) =>
  useQuery({ queryKey: [...caseKeys.detail(id), 'own'], queryFn: () => casesApi.getOwnCase(id) });

export const useCounts = (enabled: boolean) =>
  useQuery({ queryKey: caseKeys.counts, queryFn: casesApi.getCounts, enabled });

/** After any action every list, count and case may have changed. */
function useInvalidateCases() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: caseKeys.all });
}

export function useApprove() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ id, replyText, note }: { id: string; replyText: string | null; note?: string }) =>
      casesApi.approveCase(id, replyText, note),
    onSuccess: invalidate,
  });
}

export function useReject() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => casesApi.rejectCase(id, note),
    onSuccess: invalidate,
  });
}

export function useHoldingReply() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ id, replyText }: { id: string; replyText: string | null }) => casesApi.sendHoldingReply(id, replyText),
    onSuccess: invalidate,
  });
}

export const useAuditLog = (filters: AuditFilters) =>
  useQuery({ queryKey: [...caseKeys.all, 'audit', filters], queryFn: () => casesApi.listAudit(filters) });

export function useFlag() {
  const invalidate = useInvalidateCases();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => casesApi.flagCase(id, note),
    onSuccess: invalidate,
  });
}
