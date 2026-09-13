import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { JobProgress } from '../components/JobProgress';

// Mock the React Query hooks
vi.mock('../api/queries', () => ({
  useJob: vi.fn(),
  useJobDiagnostics: vi.fn(),
}));

import { useJob, useJobDiagnostics } from '../api/queries';

const mockUseJob = vi.mocked(useJob);
const mockUseJobDiagnostics = vi.mocked(useJobDiagnostics);

function setupMocks(jobData: any, diagData: any[] = []) {
  mockUseJob.mockReturnValue({
    data: jobData,
    isLoading: false,
    isError: false,
    error: null,
  } as any);

  mockUseJobDiagnostics.mockReturnValue({
    data: diagData,
    isLoading: false,
    isError: false,
    error: null,
  } as any);
}

describe('JobProgress', () => {
  it('renders PENDING state with 0% progress', () => {
    setupMocks({
      id: 'job-1',
      status: 'pending',
      progress: 0,
      checkpoint_data: null,
    });

    render(<JobProgress jobId="job-1" onRestart={() => {}} />);

    expect(screen.getByText(/JOB STATUS: PENDING/)).toBeInTheDocument();
    expect(screen.getByText('0% COMPLETE')).toBeInTheDocument();
  });

  it('renders RUNNING state with correct percentage', () => {
    setupMocks({
      id: 'job-2',
      status: 'running',
      progress: 0.65,
      checkpoint_data: null,
    });

    render(<JobProgress jobId="job-2" onRestart={() => {}} />);

    expect(screen.getByText(/JOB STATUS: RUNNING/)).toBeInTheDocument();
    expect(screen.getByText('65% COMPLETE')).toBeInTheDocument();
  });

  it('renders COMPLETE state', () => {
    setupMocks({
      id: 'job-3',
      status: 'complete',
      progress: 1.0,
      checkpoint_data: null,
    });

    render(<JobProgress jobId="job-3" onRestart={() => {}} />);

    expect(screen.getByText(/JOB STATUS: COMPLETE/)).toBeInTheDocument();
    expect(screen.getByText('100% COMPLETE')).toBeInTheDocument();
  });

  it('renders FAILED state', () => {
    setupMocks({
      id: 'job-4',
      status: 'failed',
      progress: 0.3,
      checkpoint_data: null,
    });

    render(<JobProgress jobId="job-4" onRestart={() => {}} />);

    expect(screen.getByText(/JOB STATUS: FAILED/)).toBeInTheDocument();
    expect(screen.getByText('30% COMPLETE')).toBeInTheDocument();
  });

  it('renders diagnostics with correct severity information', () => {
    const diagnostics = [
      {
        id: 'diag-1',
        job_id: 'job-5',
        chunk_id: null,
        layer_id: null,
        stage: 'mesh_validation',
        severity: 'warning',
        status: 'warning',
        code: 'THIN_WALL',
        message: 'Wall thickness below recommended minimum',
        details: null,
        created_at: '2026-09-12T10:00:00Z',
      },
      {
        id: 'diag-2',
        job_id: 'job-5',
        chunk_id: null,
        layer_id: null,
        stage: 'sectioning',
        severity: 'error',
        status: 'fail',
        code: 'EMPTY_SLICE',
        message: 'No geometry intersected at layer 42',
        details: null,
        created_at: '2026-09-12T10:00:01Z',
      },
    ];

    setupMocks(
      { id: 'job-5', status: 'running', progress: 0.5, checkpoint_data: null },
      diagnostics,
    );

    render(<JobProgress jobId="job-5" onRestart={() => {}} />);

    expect(screen.getByText(/THIN_WALL/)).toBeInTheDocument();
    expect(screen.getByText(/EMPTY_SLICE/)).toBeInTheDocument();
    expect(screen.getByText(/DIAGNOSTICS CONSOLE/)).toBeInTheDocument();
  });

  it('fires onRestart callback when button is clicked', () => {
    const onRestart = vi.fn();
    setupMocks({
      id: 'job-6',
      status: 'complete',
      progress: 1.0,
      checkpoint_data: null,
    });

    render(<JobProgress jobId="job-6" onRestart={onRestart} />);

    const button = screen.getByText('[ START NEW JOB ]');
    fireEvent.click(button);

    expect(onRestart).toHaveBeenCalledTimes(1);
  });

  it('shows loading state when job data is not yet available', () => {
    mockUseJob.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as any);
    mockUseJobDiagnostics.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as any);

    render(<JobProgress jobId="job-loading" onRestart={() => {}} />);

    expect(screen.getByText('LOADING JOB STATUS...')).toBeInTheDocument();
  });

  it('shows checkpoint data when available', () => {
    setupMocks({
      id: 'job-cp',
      status: 'running',
      progress: 0.4,
      checkpoint_data: { chunks_processed: 3, total_chunks: 10 },
    });

    render(<JobProgress jobId="job-cp" onRestart={() => {}} />);

    expect(screen.getByText(/CHECKPOINT/)).toBeInTheDocument();
    expect(screen.getByText(/chunks_processed/)).toBeInTheDocument();
  });
});
