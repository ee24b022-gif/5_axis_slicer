import { Outlet } from 'react-router-dom';
import { Layers } from 'lucide-react';

export function MainLayout() {
  return (
    <div className="flex flex-col h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="flex-none h-14 bg-gray-900 border-b border-gray-800 flex items-center px-4 shrink-0">
        <div className="flex items-center gap-2 text-blue-500">
          <Layers className="w-5 h-5" />
          <h1 className="font-semibold tracking-wide text-sm">5-AXIS SLICER</h1>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 min-h-0 overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
}
