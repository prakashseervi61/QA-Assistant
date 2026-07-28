import { useState } from 'react';
import { FiMail, FiFolder, FiUsers, FiClock, FiBookmark, FiSettings, FiMessageSquare } from 'react-icons/fi';

export default function Sidebar({ active, setActive }) {
  const navItems = [
    { name: 'Chat', icon: <FiMessageSquare />, key: 'chat' },
    { name: 'Documents', icon: <FiFolder />, key: 'documents' },
    { name: 'Collections', icon: <FiUsers />, key: 'collections' },
    { name: 'Recent', icon: <FiClock />, key: 'recent' },
    { name: 'Bookmarks', icon: <FiBookmark />, key: 'bookmarks' },
    { name: 'Settings', icon: <FiSettings />, key: 'settings' },
  ];

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-64 bg-gray-900 text-gray-200 flex flex-col p-4 space-y-2">
      <div className="flex items-center space-x-3">
        <div className="h-8 w-8 bg-gray-800 rounded flex items-center justify-center">
          <FiMessageSquare className="text-white" />
        </div>
        <span className="font-semibold text-xl text-white">QA Assistant</span>
      </div>

      <nav className="flex-1 flex flex-col space-y-1">
        {navItems.map(item => (
          <button
            key={item.key}
            onClick={() => setActive(item.key)}
            className={`flex items-center space-x-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
              active === item.key
                ? 'bg-gray-800 text-white'
                : 'hover:bg-gray-800/70 hover:text-white'
            }`}
          >
            {item.icon}
            <span>{item.name}</span>
          </button>
        ))}
      </nav>

      <div className="mt-auto border-t border-gray-800 pt-4">
        <div className="flex items-center space-x-2 text-sm">
          <div className="h-6 w-6 bg-gray-700 rounded flex items-center justify-center">
            <FiMail className="text-gray-400" />
          </div>
          <span>Your Name</span>
        </div>
        <div className="flex items-center space-x-2 text-xs text-gray-400 mt-1">
          <div className="h-5 w-5 bg-gray-700 rounded flex items-center justify-center">
            <FiMail className="text-gray-400" />
          </div>
          <span>1.2 GB / 5 GB</span>
        </div>
      </div>
    </aside>
  );
}