import { Component } from 'react';

/**
 * Last line of defense: a render error anywhere below must not blank the
 * whole app. Shows a recoverable fallback instead.
 */
export default class ErrorBoundary extends Component {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center bg-paper px-6 text-center">
          <h1 className="font-editorial text-2xl font-medium text-ink">
            Something went wrong
          </h1>
          <p className="mt-2 max-w-sm text-sm text-ink-muted">
            The app ran into an unexpected error. Reloading usually fixes it.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-subtle transition-colors hover:bg-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
          >
            Reload app
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}