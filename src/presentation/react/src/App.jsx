import { useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import CommandPalette from './components/CommandPalette';
import Dock from './components/Dock';
import TopNav from './components/TopNav';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import SettingsPanel from './components/SettingsPanel';
import HistoryView from './components/HistoryView';
import PageScroll from './components/PageScroll';
import { navItemForKey, navKeyForPath } from './components/navItems';
import { getTheme, setTheme } from './theme';

export default function App() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [isDark, setIsDark] = useState(() => getTheme() === 'dark');
  const location = useLocation();
  const navigate = useNavigate();

  // The URL is the single source of truth for which view is showing, so the
  // dock highlight, the ⌘K palette and the browser's back/forward all agree.
  const activeView = navKeyForPath(location.pathname);

  // A bare `/chat` is a fresh conversation (the New chat action); `/chat/<id>`
  // is a saved one, so the Chat link owns that highlight instead.
  const freshChat = location.pathname === '/chat';

  function handleNavigate(key) {
    navigate(navItemForKey(key).path);
  }

  /**
   * Start a fresh conversation from the dock.
   *
   * `/chat` (no id) *is* the fresh chat, so navigating there is the whole
   * action. ChatWidget reads the id off the route, so no event hand-off is
   * needed and the URL stays the single source of truth.
   */
  function handleNewChat() {
    navigate('/chat');
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
   * The id becomes the route (`/chat/<id>`), so the chat is linkable, the
   * back button steps between conversations, and a refresh lands on the same
   * conversation. ChatWidget watches the param and loads the messages.
   */
  function handleOpenConversation(id) {
    navigate(`/chat/${id}`);
  }

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
        <Dock active={activeView} freshChat={freshChat} onNewChat={handleNewChat} />

        <Routes>
          {/* `/` and `/chat` are the same fresh chat; `/chat/:conversationId`
              opens that conversation. The id is the conversation's uuid, so
              every chat gets its own address-bar id. */}
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatWidget />} />
          <Route path="/chat/:conversationId" element={<ChatWidget />} />

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
                <SettingsPanel isDark={isDark} />
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