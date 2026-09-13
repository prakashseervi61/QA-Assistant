import {
  Bookmark,
  Clock,
  FolderOpen,
  MessageSquare,
  Settings,
  Users,
} from 'lucide-react';

/**
 * Canonical navigation model for the app shell (TopNav, Dock, CommandPalette).
 * Single source of truth for every locator of a top-level view.
 */
export const navItems = [
  { key: 'chat', name: 'Chat', icon: MessageSquare, description: 'Ask questions grounded in your documents' },
  { key: 'documents', name: 'Documents', icon: FolderOpen, description: 'Upload and manage your source files' },
  { key: 'collections', name: 'Collections', icon: Users, description: 'Group documents for joint querying' },
  { key: 'recent', name: 'Recent', icon: Clock, description: 'Jump back into a previous conversation' },
  { key: 'bookmarks', name: 'Bookmarks', icon: Bookmark, description: 'Revisit saved answers and sources' },
  { key: 'settings', name: 'Settings', icon: Settings, description: 'Appearance and server configuration' },
];