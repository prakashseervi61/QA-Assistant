import { Toaster as SonnerToaster } from 'sonner';

/**
 * Toaster — themed sonner toast host. Uses theme-aware tokens so toasts
 * follow the active light/dark look; positioned above the floating dock.
 */
export default function Toaster() {
  return (
    <SonnerToaster
      position="top-center"
      toastOptions={{
        style: {
          background: 'var(--bg-surface)',
          color: 'var(--ink-primary)',
          border: '1px solid var(--border-default)',
          borderRadius: '0.75rem',
          boxShadow: 'var(--shadow-float)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
        },
      }}
      theme={undefined}
    />
  );
}