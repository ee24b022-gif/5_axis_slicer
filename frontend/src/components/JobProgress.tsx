import { useJob, useJobDiagnostics } from '../api/queries';

interface JobProgressProps {
  jobId: string;
  onRestart: () => void;
}

export function JobProgress({ jobId, onRestart }: JobProgressProps) {
  const { data: job, isLoading: jobLoading } = useJob(jobId, {
    refetchInterval: (query: any) => {
      const data = query.state?.data;
      const status = data?.status || '';
      return ['complete', 'failed', 'cancelled', 'partial'].includes(status) ? false : 1000;
    }
  });

  const { data: diagnostics, isLoading: diagLoading } = useJobDiagnostics(jobId, {
    refetchInterval: () => {
      // We rely on the job status to stop polling diagnostics as well,
      // but since diagnostics query doesn't know job status directly, 
      // we check our component's `job` state.
      const status = job?.status || '';
      return ['complete', 'failed', 'cancelled', 'partial'].includes(status) ? false : 2000;
    }
  });

  if (jobLoading && !job) {
    return <div className="accent-text">LOADING JOB STATUS...</div>;
  }
  if (!job) {
    return <div className="error-text">ERR: JOB NOT FOUND</div>;
  }

  const percent = Math.round(job.progress * 100);
  
  let statusColor = '#fff';
  if (job.status === 'complete') statusColor = '#4caf50';
  if (job.status === 'failed' || job.status === 'cancelled') statusColor = '#f44336';
  if (job.status === 'partial') statusColor = '#ff9800';
  if (job.status === 'running') statusColor = '#2196f3';

  return (
    <div className="controls-container">
      <div className="accent-text" style={{ marginBottom: '10px', color: statusColor }}>
        &gt; JOB STATUS: {job.status.toUpperCase()}
      </div>
      
      <div style={{ marginBottom: '10px' }}>
        <div style={{ width: '100%', backgroundColor: '#333', height: '20px', borderRadius: '4px', overflow: 'hidden' }}>
          <div style={{ width: `${percent}%`, backgroundColor: statusColor, height: '100%', transition: 'width 0.3s' }} />
        </div>
        <div style={{ textAlign: 'right', fontSize: '12px', marginTop: '4px' }}>
          {percent}% COMPLETE
        </div>
      </div>

      {job.checkpoint_data && Object.keys(job.checkpoint_data).length > 0 && (
        <div style={{ fontSize: '12px', marginBottom: '15px' }}>
          [CHECKPOINT]: {JSON.stringify(job.checkpoint_data)}
        </div>
      )}

      <div className="accent-text" style={{ marginBottom: '10px' }}>
        &gt; DIAGNOSTICS CONSOLE
      </div>
      
      <div style={{ 
        backgroundColor: '#111', 
        padding: '10px', 
        borderRadius: '4px', 
        height: '200px', 
        overflowY: 'auto',
        fontFamily: 'monospace',
        fontSize: '12px',
        marginBottom: '20px'
      }}>
        {diagLoading && !diagnostics && <div>Polling diagnostics...</div>}
        {diagnostics?.length === 0 && <div style={{ color: '#888' }}>[INFO] No diagnostics reported. Job processed successfully.</div>}
        {diagnostics?.map((diag) => {
          let color = '#ccc';
          if (diag.severity === 'error' || diag.severity === 'critical') color = '#f44336';
          if (diag.severity === 'warning') color = '#ff9800';
          if (diag.status === 'not_implemented') color = '#9c27b0';
          
          return (
            <div key={diag.id} style={{ color, marginBottom: '4px' }}>
              [{new Date(diag.created_at).toLocaleTimeString()}] [{diag.stage}] {diag.code}: {diag.message}
            </div>
          );
        })}
      </div>

      <button className="btn-secondary" style={{ width: '100%' }} onClick={onRestart}>
        [ START NEW JOB ]
      </button>
    </div>
  );
}
