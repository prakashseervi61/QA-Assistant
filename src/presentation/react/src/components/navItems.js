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
  { key: 'chat', name: 'Chat', icon: MessageSquare, description: 'Ask questions grounded in your documents', keywords: 'ask question new chat talk' },
  { key: 'documents', name: 'Documents', icon: FolderOpen, description: 'Upload and manage your source files', keywords: 'docs upload files source pdf' },
  { key: 'collections', name: 'Collections', icon: Users, description: 'Group documents for joint querying', keywords: 'groups folders tags' },
  { key: 'history', name: 'History', icon: Clock, description: 'Every past conversation, saved on disk', keywords: 'history past chats log archive previous recent' },
  { key: 'bookmarks', name: 'Bookmarks', icon: Bookmark, description: 'Revisit saved answers and sources', keywords: 'saved favorites stars marked' },
  { key: 'settings', name: 'Settings', icon: Settings, description: 'Appearance and server configuration', keywords: 'preferences config options' },
];