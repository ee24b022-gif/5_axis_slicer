import { ErrorBoundary } from 'react-error-boundary';
import type { FallbackProps } from 'react-error-boundary';
import { WifiOff, AlertTriangle } from 'lucide-react';

function ErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  const err = error as any;
  const isConnectionError = err?.isConnectionError || 
                           err?.message?.includes('Network Error') ||
                           err?.message?.includes('Failed to fetch');

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 text-gray-100 p-4">
      <div className="max-w-md w-full bg-gray-800 rounded-lg shadow-xl p-8 border border-gray-700 text-center">
        {isConnectionError ? (
          <>
            <WifiOff className="w-16 h-16 text-red-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">Connection Error</h2>
            <p className="text-gray-400 mb-6">
              Unable to reach the slicer backend. Please ensure the server is running and try again.
            </p>
          </>
        ) : (
          <>
            <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
            <h2 className="text-2xl font-bold mb-2">Unexpected Error</h2>
            <p className="text-gray-400 mb-4">
              Something went wrong in the application.
            </p>
            <pre className="bg-gray-900 p-4 rounded text-left text-sm overflow-auto mb-6 text-red-400">
              {err?.message}
            </pre>
          </>
        )}
        
        <button
          onClick={resetErrorBoundary}
          className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded transition-colors"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}

export function GlobalErrorBoundary({ children }: { children: React.ReactNode }) {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      {children}
    </ErrorBoundary>
  );
}
