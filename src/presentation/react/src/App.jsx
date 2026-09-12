import { useState } from 'react';
import {
  FiBookmark,
  FiDatabase,
  FiFileText,
  FiMessageSquare,
  FiSettings,
  FiSun,
  FiUsers,
} from 'react-icons/fi';
import Sidebar from './components/Sidebar';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import EmptyState from './components/EmptyState';
import RecentView from './components/RecentView';
import './App.css'; // optional custom styles

/** Static settings overview — informational only, no client-side behavior. */
function SettingsPanel() {
  const sections = [
    {
      icon: FiSun,
      title: 'Appearance',
      description: 'Warm paper light or carbon dark theme — from a single design token.',
      value: 'Light · Dark',
    },
    {
      icon: FiMessageSquare,
      title: 'Chat answers',
      description: 'Responses are generated from your documents and include source citations.',
      value: 'RAG',
    },
    {
      icon: FiFileText,
      title: 'Supported formats',
      description: 'Upload PDF, DOCX or TXT files to make them searchable.',
      value: 'PDF · DOCX · TXT',
    },
    {
      icon: FiDatabase,
      title: 'Data storage',
      description: 'Embeddings and metadata are stored locally on this machine.',
      value: 'Local',
    },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h2 className="font-editorial flex items-center gap-2 text-2xl font-medium tracking-tight text-ink">
        <FiSettings className="text-brand-600" />
        Settings
      </h2>
      <p className="text-sm text-ink-muted">
        This app is configured by the server. Nothing here is editable in the UI yet.
      </p>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {sections.map(section => {
          const Icon = section.icon;
          return (
            <li key={section.title} className="flex items-center gap-4 px-4 py-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
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
  const [sidebarOpen, setSidebarOpen] = useState(
    () => window.matchMedia('(min-width: 1024px)').matches
  );

  function handleNavigate(key) {
    setActiveView(key);
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
            icon={FiUsers}
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
            icon={FiBookmark}
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
    <div className="flex h-screen overflow-hidden bg-paper">
      {/* Nav drawer backdrop (mobile only — sidebar is in-flow on desktop) */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        active={activeView}
        onNavigate={handleNavigate}
        open={sidebarOpen}
        onToggle={() => setSidebarOpen(prev => !prev)}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main column — Chat is the primary view */}
      <main className="flex min-h-0 flex-1 flex-col">
        {activeView === 'chat' ? (
          <ChatWidget />
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">{renderView()}</div>
        )}
      </main>
    </div>
  );
}