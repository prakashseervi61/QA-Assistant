import { useState } from 'react';
import Sidebar from './components/Sidebar';
import DocumentList from './components/DocumentList';
import ChatWidget from './components/ChatWidget';
import './App.css'; // optional custom styles

export default function App() {
  const [activeView, setActiveView] = useState('documents'); // default view

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <Sidebar active={activeView} setActive={setActiveView} />

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="bg-white shadow-sm px-6 py-4 border-b">
          <h1 className="text-xl font-semibold">QA Assistant</h1>
        </header>

        <div className="flex flex-1 overflow-hidden">
          {/* Content area (documents, settings, etc.) */}
          <main className="flex-1 p-4 overflow-y-auto bg-white">
            {activeView === 'documents' && (
              <div>
                <h2 className="mb-2 text-lg font-semibold">Documents</h2>
                <DocumentList />
              </div>
            )}
            {activeView === 'chat' && (
              <div>
                <h2 className="mb-2 text-lg font-semibold">Chat</h2>
                <ChatWidget conversationId={null} />
              </div>
            )}
            {(!['documents', 'chat'].includes(activeView)) && (
              <div className="text-center py-12 text-gray-500">
                {activeView === 'settings' && (
                  <>
                    <h2 className="mb-4 text-lg font-semibold">Settings</h2>
                    <p>Settings panel coming soon.</p>
                  </>
                )}
                {activeView === 'collections' && (
                  <>
                    <h2 className="mb-4 text-lg font-semibold">Collections</h2>
                    <p>Collections view coming soon.</p>
                  </>
                )}
                {activeView === 'recent' && (
                  <>
                    <h2 className="mb-4 text-lg font-semibold">Recent</h2>
                    <p>Recent view coming soon.</p>
                  </>
                )}
                {activeView === 'bookmarks' && (
                  <>
                    <h2 className="mb-4 text-lg font-semibold">Bookmarks</h2>
                    <p>Bookmarks view coming soon.</p>
                  </>
                )}
              </div>
            )}
          </main>

          {/* Chat sidebar (always visible) */}
          <section className="w-80 border-l border-gray-200 flex flex-col bg-gray-50">
            <div className="flex-1 overflow-y-auto p-4">
              <h2 className="mb-2 text-lg font-semibold">Chat</h2>
              <ChatWidget conversationId={null} />
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}