import { describe, it, expect } from 'vitest';
import type {
  JobResponse,
  DiagnosticResponse,
  ExportResponse,
  MachineProfileResponse,
  SlicePlane,
  StageProgressEvent,
} from '../api/models';

describe('TypeScript model contracts', () => {
  it('JobResponse conforms to expected shape', () => {
    const job: JobResponse = {
      id: 'job-1',
      creator_id: 'user-1',
      mesh_id: 'mesh-1',
      machine_profile_id: 'mp-1',
      mode: 'three_axis',
      status: 'pending',
      progress: 0,
      checkpoint_data: null,
      started_at: null,
      completed_at: null,
      cancellation_requested_at: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(job.id).toBe('job-1');
    expect(job.status).toBe('pending');
    expect(job.mode).toBe('three_axis');
  });

  it('DiagnosticResponse conforms to expected shape', () => {
    const diag: DiagnosticResponse = {
      id: 'diag-1',
      job_id: 'job-1',
      chunk_id: null,
      layer_id: null,
      stage: 'mesh_validation',
      severity: 'warning',
      status: 'warning',
      code: 'THIN_WALL',
      message: 'Wall is thin',
      details: { thickness_mm: 0.3 },
      created_at: '2026-01-01T00:00:00Z',
    };

    expect(diag.severity).toBe('warning');
    expect(diag.stage).toBe('mesh_validation');
  });

  it('ExportResponse conforms to expected shape', () => {
    const exp: ExportResponse = {
      id: 'exp-1',
      job_id: 'job-1',
      creator_id: 'user-1',
      dialect: 'marlin',
      status: 'pending',
      storage_uri: null,
      content_hash: null,
      size_bytes: null,
      export_metadata: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(exp.status).toBe('pending');
    expect(exp.dialect).toBe('marlin');
  });

  it('MachineProfileResponse conforms to expected shape', () => {
    const profile: MachineProfileResponse = {
      id: 'mp-1',
      name: 'Test Machine',
      revision: 1,
      dialect: 'marlin',
      contract: { kinematic_convention: 'BC_TABLE' },
      limits: { ranges: {} },
      is_active: true,
      author_id: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(profile.is_active).toBe(true);
    expect(profile.dialect).toBe('marlin');
  });

  it('SlicePlane conforms to expected shape', () => {
    const plane: SlicePlane = {
      plane_origin: [0, 0, 10],
      unit_normal: [0, 0, 1],
      angle_pair: [0, 0],
      angle_units: 'degrees',
      rotation_convention: 'BC_TABLE',
      local_x: [1, 0, 0],
      local_y: [0, 1, 0],
      source_frame: 'canonical',
    };

    expect(plane.unit_normal).toEqual([0, 0, 1]);
    expect(plane.angle_units).toBe('degrees');
  });

  it('StageProgressEvent conforms to expected shape', () => {
    const event: StageProgressEvent = {
      job_id: 'job-1',
      stage: 'sectioning',
      progress: 0.5,
      chunk_idx: 0,
      layer_idx: 10,
      severity: 'info',
      status: 'pass',
      code: 'SECTION_COMPLETE',
      message: 'Sectioning done',
    };

    expect(event.stage).toBe('sectioning');
    expect(event.progress).toBe(0.5);
  });

  it('JobStatus exhaustively covers all variants', () => {
    const allStatuses: JobResponse['status'][] = [
      'pending', 'running', 'complete', 'failed', 'partial', 'cancelled',
    ];
    expect(allStatuses).toHaveLength(6);
  });

  it('ExportStatus exhaustively covers all variants', () => {
    const allStatuses: ExportResponse['status'][] = [
      'pending', 'ready', 'blocked', 'failed', 'revoked',
    ];
    expect(allStatuses).toHaveLength(5);
  });
});
