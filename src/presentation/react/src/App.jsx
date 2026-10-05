import { useEffect, useRef, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Database, FileText, MessageSquare, Sun } from 'lucide-react';
import CommandPalette from './components/CommandPalette';
import Dock from './components/Dock';
import TopNav from './components/TopNav';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import HistoryView from './components/HistoryView';
import PageScroll from './components/PageScroll';
import { navItemForKey, navKeyForPath } from './components/navItems';
import { getTheme, setTheme } from './theme';

/** Static settings overview — informational only, no client-side behavior. */
function SettingsPanel() {
  const sections = [
    {
      icon: Sun,
      title: 'Appearance',
      description: 'Paper beige light or flat black dark — one token layer, no per-component overrides.',
      value: 'Light · Dark',
      tile: 'nb-tile-yellow',
    },
    {
      icon: MessageSquare,
      title: 'Chat answers',
      description: 'Responses are generated from your documents and include source citations.',
      value: 'RAG',
      tile: 'nb-tile-cyan',
    },
    {
      icon: FileText,
      title: 'Supported formats',
      description: 'Upload PDF, DOCX or TXT files to make them searchable.',
      value: 'PDF · DOCX · TXT',
      tile: 'nb-tile-pink',
    },
    {
      icon: Database,
      title: 'Data storage',
      description: 'Embeddings and saved history are stored locally on this machine.',
      value: 'Local',
      tile: 'nb-tile-green',
    },
  ];

  return (
    <div className="mx-auto max-w-3xl">
      <span className="nb-tag">Settings</span>
      <h2 className="mt-4 text-3xl font-black uppercase text-ink sm:text-4xl">
        Configuration
      </h2>
      <p className="mt-3 max-w-xl text-base leading-relaxed text-ink-secondary">
        This app is configured by the server. Nothing here is editable in the UI yet.
      </p>

      <ul className="nb-bento mt-8">
        {sections.map(section => {
          const Icon = section.icon;
          return (
            <li key={section.title} className={`nb-card ${section.tile} flex flex-col gap-3 p-6`}>
              <div className="flex h-11 w-11 items-center justify-center rounded border-[3px] border-nb-line bg-paper-surface text-ink">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </div>
              <p className="text-lg font-extrabold uppercase tracking-tight text-ink-on-accent">
                {section.title}
              </p>
              <p className="text-sm font-medium leading-relaxed text-ink-on-accent-muted">
                {section.description}
              </p>
              <span className="nb-chip mt-auto self-start !bg-paper-surface font-mono text-[11px] uppercase">
                {section.value}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function App() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [isDark, setIsDark] = useState(() => getTheme() === 'dark');
  const location = useLocation();
  const navigate = useNavigate();
  const pendingConversation = useRef(null);

  // The URL is the single source of truth for which view is showing, so the
  // dock highlight, the ⌘K palette and the browser's back/forward all agree.
  const activeView = navKeyForPath(location.pathname);

  function handleNavigate(key) {
    navigate(navItemForKey(key).path);
  }

  function handleToggleTheme() {
    setIsDark(prev => {
      const next = prev ? 'light' : 'dark';
      setTheme(next);
      return next === 'dark';
    });
  }

  /**
   * Open a saved conversation from the History view.
   *
   * ChatWidget listens for this event, but it is only mounted on `/`, so when
   * we arrive from another page the dispatch has to wait until after the
   * route renders. Child effects run before the parent's, so an effect here
   * fires once ChatWidget's listener is attached.
   */
  function handleOpenConversation(id) {
    if (location.pathname === '/') {
      window.dispatchEvent(new CustomEvent('open-conversation', { detail: id }));
      return;
    }
    pendingConversation.current = id;
    navigate('/');
  }

  useEffect(() => {
    if (location.pathname === '/' && pendingConversation.current) {
      const id = pendingConversation.current;
      pendingConversation.current = null;
      window.dispatchEvent(new CustomEvent('open-conversation', { detail: id }));
    }
  }, [location.pathname]);

  // pb-20 clears the mobile bottom nav bar; the dock is a left rail on lg.
  const pagePad = 'p-4 pb-24 sm:p-6 sm:pb-24 lg:px-28 lg:py-8 lg:pb-8';

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-paper">
      {/* First tab stop: lets a keyboard user jump straight past the nav rail
          and the ⌘K trigger into the view they came for. */}
      <a href="#main-content" className="nb-skip-link">
        Skip to content →
      </a>

      <TopNav
        isDark={isDark}
        onToggleTheme={handleToggleTheme}
        onOpenPalette={() => setPaletteOpen(true)}
      />

      {/* Main column — Chat is the primary view at "/". tabIndex -1 so the
          skip link can move focus here; focus:outline-none because the skip
          link itself is the visible affordance. */}
      <main
        id="main-content"
        tabIndex={-1}
        className="relative flex min-h-0 flex-1 flex-col focus:outline-none"
      >
        <Dock active={activeView} />

        <Routes>
          <Route path="/" element={<ChatWidget />} />

          <Route
            path="/documents"
            element={
              <PageScroll className={pagePad}>
                <DocumentList />
              </PageScroll>
            }
          />

          <Route
            path="/history"
            element={
              <PageScroll className={pagePad}>
                <HistoryView onOpen={handleOpenConversation} />
              </PageScroll>
            }
          />

          <Route
            path="/settings"
            element={
              <PageScroll className={pagePad}>
                <SettingsPanel />
              </PageScroll>
            }
          />

          {/* Unknown URL: send the visitor to chat rather than a blank page. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <CommandPalette
        open={paletteOpen}
        onOpen={() => setPaletteOpen(true)}
        onClose={() => setPaletteOpen(false)}
        active={activeView}
        onNavigate={handleNavigate}
        isDark={isDark}
        onToggleTheme={handleToggleTheme}
      />
    </div>
  );
}