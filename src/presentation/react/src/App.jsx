import { useState } from 'react';
import {
  Bookmark,
  Database,
  FileText,
  MessageSquare,
  Settings,
  Sun,
  Users,
} from 'lucide-react';
import CommandPalette from './components/CommandPalette';
import Dock from './components/Dock';
import TopNav from './components/TopNav';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import EmptyState from './components/EmptyState';
import RecentView from './components/RecentView';
import { Toaster } from './components/ui';
import { getTheme, setTheme } from './theme';
import './App.css'; // optional custom styles

/** Static settings overview — informational only, no client-side behavior. */
function SettingsPanel() {
  const sections = [
    {
      icon: Sun,
      title: 'Appearance',
      description: 'Warm paper light or carbon dark theme — from a single design token.',
      value: 'Light · Dark',
    },
    {
      icon: MessageSquare,
      title: 'Chat answers',
      description: 'Responses are generated from your documents and include source citations.',
      value: 'RAG',
    },
    {
      icon: FileText,
      title: 'Supported formats',
      description: 'Upload PDF, DOCX or TXT files to make them searchable.',
      value: 'PDF · DOCX · TXT',
    },
    {
      icon: Database,
      title: 'Data storage',
      description: 'Embeddings and metadata are stored locally on this machine.',
      value: 'Local',
    },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h2 className="font-editorial flex items-center gap-2 text-2xl font-medium tracking-tight text-ink">
        <span className="bg-bioluminescent flex h-9 w-9 items-center justify-center rounded-xl text-white shadow-glow-violet">
          <Settings className="h-[18px] w-[18px]" aria-hidden="true" />
        </span>
        Settings
      </h2>
      <p className="text-sm text-ink-muted">
        This app is configured by the server. Nothing here is editable in the UI yet.
      </p>
      <ul className="glass divide-y divide-border overflow-hidden rounded-2xl shadow-card">
        {sections.map(section => {
          const Icon = section.icon;
          return (
            <li key={section.title} className="flex items-center gap-4 px-4 py-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-paper-100 text-brand-500">
                <Icon className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{section.title}</p>
                <p className="text-sm text-ink-muted">{section.description}</p>
              </div>
              <span className="shrink-0 rounded-full bg-paper-200 px-2.5 py-1 text-xs font-medium text-ink-secondary">
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
  const [activeView, setActiveView] = useState('chat');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [isDark, setIsDark] = useState(() => getTheme() === 'dark');

  function handleNavigate(key) {
    setActiveView(key);
  }

  function handleToggleTheme() {
    setIsDark(prev => {
      const next = prev ? 'light' : 'dark';
      setTheme(next);
      return next === 'dark';
    });
  }

  function handleOpenRecentConversation(id) {
    window.dispatchEvent(new CustomEvent('open-conversation', { detail: id }));
    setActiveView('chat');
  }

  function renderView() {
    switch (activeView) {
      case 'documents':
        return <DocumentList />;
      case 'collections':
        return (
          <EmptyState
            icon={Users}
            title="No collections yet"
            description="Group related documents so you can query them together. Collections will appear here once they are created."
            hint="Create collections from the server or future releases."
          />
        );
      case 'recent':
        return <RecentView onOpen={handleOpenRecentConversation} />;
      case 'bookmarks':
        return (
          <EmptyState
            icon={Bookmark}
            title="No bookmarks yet"
            description="Save important answers and documents to revisit them later. Bookmarks will appear here."
          />
        );
      case 'settings':
        return <SettingsPanel />;
      default:
        return null;
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-paper">
      <Toaster />

      <TopNav
        isDark={isDark}
        onToggleTheme={handleToggleTheme}
        onOpenPalette={() => setPaletteOpen(true)}
      />

      {/* Main column — Chat is the primary view */}
      <main className="relative flex min-h-0 flex-1 flex-col">
        <Dock active={activeView} onNavigate={handleNavigate} />
        {activeView === 'chat' ? (
          <ChatWidget />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6 lg:px-24 lg:py-8">{renderView()}</div>
        )}
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