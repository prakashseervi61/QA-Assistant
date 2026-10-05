import { Toaster as SonnerToaster } from 'sonner';

/**
 * Toaster — themed sonner toast host. Uses theme-aware tokens so toasts
 * follow the active light/dark look; positioned below the top nav so it never
 * collides with the mobile dock.
 *
 * Every colour is a token rather than a literal, and `theme` is left undefined
 * so sonner emits no stylesheet of its own that could disagree with them.
 */
export default function Toaster() {
  return (
    <SonnerToaster
      position="top-center"
      toastOptions={{
        style: {
          background: 'var(--bg-surface)',
          color: 'var(--ink-primary)',
          // Hard border + hard shadow, no blur, 4px radius — same rules as
          // every other surface in the app.
          border: '3px solid var(--nb-line)',
          borderRadius: '4px',
          boxShadow: '5px 5px 0 var(--nb-shadow-color)',
          fontFamily: "'Space Grotesk', Inter, system-ui, sans-serif",
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.02em',
        },
      }}
      theme={undefined}
    />
  );
}
