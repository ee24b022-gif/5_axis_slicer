import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fetchMachineProfiles } from '../api/queries';
import { apiClient } from '../api/client';
import type { MachineProfileResponse } from '../api/models';

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

const mockGet = apiClient.get as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGet.mockReset();
});

function minimalProfile(overrides: Partial<MachineProfileResponse> = {}): MachineProfileResponse {
  return {
    id: '00000000-0000-0000-0000-000000000001',
    name: 'fractal_5_pro_provisional',
    revision: 1,
    dialect: 'klipper_manual_stepper_ab',
    contract: {},
    limits: {},
    is_active: true,
    author_id: '00000000-0000-0000-0000-000000000001',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as MachineProfileResponse;
}

describe('fetchMachineProfiles', () => {
  it('returns the array for a valid JSON array response', async () => {
    const profiles = [minimalProfile()];
    mockGet.mockResolvedValueOnce({ data: profiles });

    const result = await fetchMachineProfiles();

    expect(result).toEqual(profiles);
  });

  it('returns data.items when the backend wraps results in an object', async () => {
    const profiles = [minimalProfile()];
    mockGet.mockResolvedValueOnce({ data: { items: profiles, total: 1 } });

    const result = await fetchMachineProfiles();

    expect(result).toEqual(profiles);
  });

  it('throws on an HTML (non-JSON) response', async () => {
    mockGet.mockResolvedValueOnce({ data: '<html><body>Internal Server Error</body></html>' });

    await expect(fetchMachineProfiles()).rejects.toThrow(/machine profiles/i);
  });

  it('throws on a malformed JSON payload', async () => {
    mockGet.mockResolvedValueOnce({ data: null });

    await expect(fetchMachineProfiles()).rejects.toThrow(/machine profiles/i);
  });

  it('throws on an unexpected object shape', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: 'not-an-array' } });

    await expect(fetchMachineProfiles()).rejects.toThrow(/machine profiles/i);
  });

  it('propagates non-2xx responses instead of degrading to []', async () => {
    const error: any = new Error('Bad request');
    error.response = { status: 500, data: 'Server error' };
    error.isAxiosError = true;
    mockGet.mockRejectedValueOnce(error);

    await expect(fetchMachineProfiles()).rejects.toThrow();
  });
});
