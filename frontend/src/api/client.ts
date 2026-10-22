import axios from 'axios';

// Base URL for all API requests. VITE_API_BASE_URL is preferred; VITE_API_URL
// is honored as a compatibility fallback. Neither defaults to a hardcoded
// deployment URL - without either variable, requests are relative to the
// serving origin (/api, proxied to the backend in dev via vite.config.ts).
// Production: set VITE_API_BASE_URL in the frontend hosting environment to the
// public backend URL, e.g. https://api.example.com
const baseURL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL || '/api';

if (import.meta.env.DEV && !localStorage.getItem('access_token')) {
  localStorage.setItem('access_token', 'DEV_MOCK_ACCESS_TOKEN');
}

export const apiClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to inject access token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
}, (error) => Promise.reject(error));

// Function to refresh the access token
async function refreshAccessToken(): Promise<string> {
  // Use a separate axios instance or plain fetch to avoid interceptor loops
  const response = await axios.post(`${baseURL}/auth/refresh`, {}, {
    withCredentials: true,
  });
  return response.data.access_token;
}

// Response interceptor to handle global errors (like connection errors or 401s)
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Check if it's a network error (no response received from server)
    if (!error.response && error.request) {
      console.error("Network Error or Backend is unreachable:", error.message);
      // We attach a special property to easily identify connection errors in our ErrorBoundary
      error.isConnectionError = true;
      return Promise.reject(error);
    }
    
    const originalRequest = error.config;
    // If unauthorized and we haven't retried yet
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Don't intercept refresh token failures to prevent infinite loops
      if (originalRequest.url === '/auth/refresh') {
        return Promise.reject(error);
      }
      
      originalRequest._retry = true;
      try {
        const newToken = await refreshAccessToken();
        localStorage.setItem('access_token', newToken);
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed, user needs to login again
        localStorage.removeItem('access_token');
        alert("Session expired. Please log in again.");
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }
    
    // Pass the error up to the caller to handle or let the ErrorBoundary catch it
    return Promise.reject(error);
  }
);