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
          <div className="nb-card nb-card-dark max-w-md p-10">
            <span className="nb-tag">Error</span>
            <h1 className="mt-4 text-3xl font-black uppercase text-paper sm:text-4xl">
              Something went wrong
            </h1>
            <p className="mt-3 text-base font-medium leading-relaxed text-ink-on-inverse-muted">
              The app ran into an unexpected error. Reloading usually fixes it.
            </p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="nb-btn nb-focus nb-btn-primary mt-6"
            >
              Reload app →
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}