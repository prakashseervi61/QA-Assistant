import { useState } from 'react';
import {
  FiBookmark,
  FiClock,
  FiDatabase,
  FiFileText,
  FiMenu,
  FiMessageSquare,
  FiSettings,
  FiSun,
  FiUsers,
  FiX,
} from 'react-icons/fi';
import Sidebar from './components/Sidebar';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import EmptyState from './components/EmptyState';
import './App.css'; // optional custom styles

const VIEW_LABELS = {
  documents: 'Documents',
  collections: 'Collections',
  recent: 'Recent',
  bookmarks: 'Bookmarks',
  settings: 'Settings',
};

/** Static settings overview — informational only, no client-side behavior. */
function SettingsPanel() {
  const sections = [
    {
      icon: FiSun,
      title: 'Appearance',
      description: 'Light theme with an indigo accent. Colors come from a single design token.',
      value: 'Light',
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
      <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900">
        <FiSettings className="text-brand-600" />
        Settings
      </h2>
      <p className="text-sm text-slate-500">
        This app is configured by the server. Nothing here is editable in the UI yet.
      </p>
      <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
        {sections.map(section => {
          const Icon = section.icon;
          return (
            <li key={section.title} className="flex items-center gap-4 px-4 py-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-600">
                <Icon className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-900">{section.title}</p>
                <p className="text-sm text-slate-500">{section.description}</p>
              </div>
              <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
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
  const [activeView, setActiveView] = useState('documents');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  function handleNavigate(key) {
    setActiveView(key);
    setSidebarOpen(false);
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
        return (
          <EmptyState
            icon={FiClock}
            title="Nothing recent yet"
            description="Documents you open and conversations you have will show up here for quick access."
          />
        );
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
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Mobile nav drawer backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        active={activeView}
        onNavigate={handleNavigate}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open navigation menu"
            className="rounded-md p-2 text-slate-600 transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 lg:hidden"
          >
            <FiMenu className="h-5 w-5" />
          </button>
          <h1 className="text-base font-semibold text-slate-900">QA Assistant</h1>
          <span className="hidden text-sm text-slate-500 sm:block">
            / {VIEW_LABELS[activeView] ?? 'Home'}
          </span>
          <div className="ml-auto">
            <button
              type="button"
              onClick={() => setChatOpen(true)}
              aria-label="Open chat panel"
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 lg:hidden"
            >
              <FiMessageSquare className="h-4 w-4 text-brand-600" />
              Chat
            </button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">{renderView()}</main>
      </div>

      {/* Chat panel — always visible on desktop, slide-over drawer on mobile */}
      {chatOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setChatOpen(false)}
          aria-hidden="true"
        />
      )}
      <section
        aria-label="Chat"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md transform flex-col border-l border-slate-200 bg-white shadow-2xl transition-transform duration-200 ease-in-out sm:w-96 lg:static lg:z-auto lg:max-w-none lg:w-80 lg:translate-x-0 lg:shadow-none ${
          chatOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FiMessageSquare className="h-4 w-4 text-brand-600" />
            Chat
          </h2>
          <button
            type="button"
            onClick={() => setChatOpen(false)}
            aria-label="Close chat panel"
            className="rounded-md p-1.5 text-slate-500 transition-colors hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 lg:hidden"
          >
            <FiX className="h-5 w-5" />
          </button>
        </div>
        <ChatWidget conversationId={null} />
      </section>
    </div>
  );
}
