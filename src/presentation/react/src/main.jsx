import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import App from './App';
import ErrorBoundary from './components/ErrorBoundary';
import { applyTheme, getTheme } from './theme';
import './index.css';

applyTheme(getTheme());

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      {/* reducedMotion="user" makes every framer-motion animation below respect
          the OS "reduce motion" setting — the springs, hover lifts and tap
          scales across Dock, DocumentList, HistoryView, CommandPalette,
          EmptyState and WaveformOrb all collapse to instant state changes for
          anyone who asked the OS not to animate things. Declared once here
          rather than guarding ~22 animation sites individually. */}
      <MotionConfig reducedMotion="user">
        {/* BrowserRouter gives every view a real URL, so pages are linkable
            and reachable with the back/forward buttons. */}
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </MotionConfig>
    </ErrorBoundary>
  </React.StrictMode>
);