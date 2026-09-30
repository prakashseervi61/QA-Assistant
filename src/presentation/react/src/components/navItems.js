import {
  Bookmark,
  Clock,
  FolderOpen,
  MessageSquare,
  Settings,
  Users,
} from 'lucide-react';

/**
 * Canonical navigation model for the app shell (TopNav, Dock, CommandPalette)
 * and the router table in App.jsx.
 *
 * Single source of truth for every locator of a top-level view. `path` is the
 * real URL for the view, so every page is linkable, bookmarkable and reachable
 * with the back/forward buttons.
 */
export const navItems = [
  { key: 'chat', path: '/', name: 'Chat', icon: MessageSquare, description: 'Ask questions grounded in your documents', keywords: 'ask question new chat talk home' },
  { key: 'documents', path: '/documents', name: 'Documents', icon: FolderOpen, description: 'Upload and manage your source files', keywords: 'docs upload files source pdf' },
  { key: 'collections', path: '/collections', name: 'Collections', icon: Users, description: 'Group documents for joint querying', keywords: 'groups folders tags' },
  { key: 'history', path: '/history', name: 'History', icon: Clock, description: 'Every past conversation, saved on disk', keywords: 'history past chats log archive previous recent' },
  { key: 'bookmarks', path: '/bookmarks', name: 'Bookmarks', icon: Bookmark, description: 'Revisit saved answers and sources', keywords: 'saved favorites stars marked' },
  { key: 'settings', path: '/settings', name: 'Settings', icon: Settings, description: 'Appearance and server configuration', keywords: 'preferences config options' },
];

/** Look up the nav item that owns a pathname (used to highlight the shell). */
export function navKeyForPath(pathname) {
  const match = navItems.find(item =>
    item.path === '/' ? pathname === '/' : pathname.startsWith(item.path)
  );
  return match ? match.key : 'chat';
}

/** Look up a nav item by key. */
export function navItemForKey(key) {
  return navItems.find(item => item.key === key) || navItems[0];
}