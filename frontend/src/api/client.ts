import axios from 'axios';

// The base URL can be defined through environment variables, typically handled by Vite using import.meta.env
// For development it's often convenient to point to the local backend proxy.
const baseURL = import.meta.env.VITE_API_URL || '/api';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor to handle global errors (like connection errors or 401s)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Check if it's a network error (no response received from server)
    if (!error.response && error.request) {
      console.error("Network Error or Backend is unreachable:", error.message);
      // We attach a special property to easily identify connection errors in our ErrorBoundary
      error.isConnectionError = true;
    }
    
    // Pass the error up to the caller to handle or let the ErrorBoundary catch it
    return Promise.reject(error);
  }
);
