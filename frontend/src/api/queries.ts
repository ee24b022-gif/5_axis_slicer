import { useQuery, useMutation } from '@tanstack/react-query';
import type { UseQueryOptions, UseMutationOptions } from '@tanstack/react-query';
import { apiClient } from './client';
import type {
  MachineProfileResponse,
  JobResponse,
  DiagnosticResponse,
  PreviewResponse,
  JobCreateRequest,
} from './models';

// Query Keys
export const queryKeys = {
  machineProfiles: ['machineProfiles'] as const,
  job: (jobId: string) => ['jobs', jobId] as const,
  jobDiagnostics: (jobId: string) => ['jobs', jobId, 'diagnostics'] as const,
  jobPreview: (jobId: string, params?: { chunk_idx?: number, layer_idx_min?: number, layer_idx_max?: number }) => ['jobs', jobId, 'preview', params] as const,
};

// API Functions
async function fetchMachineProfiles(): Promise<MachineProfileResponse[]> {
  const { data } = await apiClient.get('/machine-profiles');
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

async function fetchJob(jobId: string): Promise<JobResponse> {
  const { data } = await apiClient.get(`/jobs/${jobId}`);
  return data;
}

async function fetchJobDiagnostics(jobId: string): Promise<DiagnosticResponse[]> {
  const { data } = await apiClient.get(`/jobs/${jobId}/diagnostics`);
  return data;
}

async function fetchJobPreview(jobId: string, params?: { chunk_idx?: number, layer_idx_min?: number, layer_idx_max?: number }): Promise<PreviewResponse> {
  const { data } = await apiClient.get(`/jobs/${jobId}/preview`, { params });
  return data;
}

async function submitJob(request: JobCreateRequest): Promise<JobResponse> {
  const { data } = await apiClient.post('/jobs', request);
  return data;
}

interface UploadMeshResponse {
  id: string;
  hash: string;
}

async function uploadMesh(formData: FormData, onUploadProgress?: (progressEvent: any) => void): Promise<UploadMeshResponse> {
  const { data } = await apiClient.post('/meshes', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  });
  return data;
}

// React Query Hooks
export function useMachineProfiles(options?: Omit<UseQueryOptions<MachineProfileResponse[]>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: queryKeys.machineProfiles,
    queryFn: fetchMachineProfiles,
    ...options,
  });
}

export function useJob(jobId: string, options?: Omit<UseQueryOptions<JobResponse>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: () => fetchJob(jobId),
    enabled: !!jobId,
    ...options,
  });
}

export function useJobDiagnostics(jobId: string, options?: Omit<UseQueryOptions<DiagnosticResponse[]>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: queryKeys.jobDiagnostics(jobId),
    queryFn: () => fetchJobDiagnostics(jobId),
    enabled: !!jobId,
    ...options,
  });
}

export function useJobPreview(jobId: string, params?: { chunk_idx?: number, layer_idx_min?: number, layer_idx_max?: number }, options?: Omit<UseQueryOptions<PreviewResponse>, 'queryKey' | 'queryFn'>) {
  return useQuery({
    queryKey: queryKeys.jobPreview(jobId, params),
    queryFn: () => fetchJobPreview(jobId, params),
    enabled: !!jobId,
    ...options,
  });
}

export function useSubmitJob(options?: Omit<UseMutationOptions<JobResponse, unknown, JobCreateRequest>, 'mutationFn'>) {
  return useMutation({
    mutationFn: submitJob,
    ...options,
  });
}

export function useUploadMesh(options?: Omit<UseMutationOptions<UploadMeshResponse, unknown, { formData: FormData, onUploadProgress?: (progressEvent: any) => void }>, 'mutationFn'>) {
  return useMutation({
    mutationFn: ({ formData, onUploadProgress }) => uploadMesh(formData, onUploadProgress),
    ...options,
  });
}
