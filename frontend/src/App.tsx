import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { GlobalErrorBoundary } from './components/GlobalErrorBoundary';
import { MainLayout } from './layouts/MainLayout';
import Home from './pages/Home';
import './index.css';

const queryClient = new QueryClient();

export default function App() {
  return (
    <GlobalErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<MainLayout />}>
              <Route index element={<Home />} />
              {/* Additional routes will be nested here in the future */}
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </GlobalErrorBoundary>
  );
}
