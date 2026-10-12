import {
  Clock,
  FolderOpen,
  MessageSquare,
  Settings,
  SquarePen,
} from 'lucide-react';

/**
 * Canonical navigation model for the app shell (TopNav, Dock, CommandPalette)
 * and the router table in App.jsx.
 *
 * Single source of truth for every locator of a top-level view. `path` is the
 * real URL for the view, so every page is linkable and reachable
 * with the back/forward buttons.
 *
 * `newChatAction` is not a route: it starts a fresh conversation from anywhere
 * in the shell, so it is exposed separately from `navItems` and rendered as a
 * button (not a link) by the Dock.
 */
export const newChatAction = {
  key: 'new-chat',
  name: 'New chat',
  icon: SquarePen,
  description: 'Start a fresh conversation',
  keywords: 'new chat fresh empty start clear reset',
};

export const navItems = [
  { key: 'chat', path: '/chat', name: 'Chat', icon: MessageSquare, description: 'Ask questions grounded in your documents', keywords: 'ask question chat talk home' },
  { key: 'history', path: '/history', name: 'History', icon: Clock, description: 'Every past conversation, saved on disk', keywords: 'history past chats log archive previous recent' },
  { key: 'documents', path: '/documents', name: 'Documents', icon: FolderOpen, description: 'Upload and manage your source files', keywords: 'docs upload files source pdf' },
  { key: 'settings', path: '/settings', name: 'Settings', icon: Settings, description: 'Appearance and server configuration', keywords: 'preferences config options' },
];

/**
 * Look up the nav item that owns a pathname (used to highlight the shell).
 *
 * Prefix match, so `/chat/<conversationId>` still resolves to the Chat item
 * and the dock stays highlighted while a specific conversation is open.
 */
export function navKeyForPath(pathname) {
  const match = navItems.find(item => pathname.startsWith(item.path));
  return match ? match.key : 'chat';
}

/** Look up a nav item by key. */
export function navItemForKey(key) {
  return navItems.find(item => item.key === key) || navItems[0];
}

/**
 * Rotating accent grounds for the navigation surfaces (the desktop Dock rail and
 * the mobile drawer), so no two adjacent items share a colour — the bento "no
 * two neighbours match" rule applied to navigation.
 *
 * These are solid accents, not pastels: a label sits on the ground, so the
 * ground has to carry body text at AA in both themes.
 *
 * Each entry pairs the *selected* ground with the ground it previews on hover,
 * so every icon flashes its own colour rather than one shared highlight.
 * The pairs are written out in full instead of interpolated ("hover:" + accent)
 * because Tailwind's scanner only emits classes it can see verbatim.
 *
 * Lives here rather than in either component so the two navigation surfaces
 * cannot drift out of sync and end up with different rotations.
 */
export const NAV_ACCENTS = [
  {
    on: 'bg-accent-yellow text-ink-on-accent',
    hover: 'hover:bg-accent-yellow hover:text-ink-on-accent hover:shadow-brutal-sm',
  },
  {
    on: 'bg-accent-cyan text-ink-on-accent',
    hover: 'hover:bg-accent-cyan hover:text-ink-on-accent hover:shadow-brutal-sm',
  },
  {
    on: 'bg-accent-magenta text-ink-on-accent',
    hover: 'hover:bg-accent-magenta hover:text-ink-on-accent hover:shadow-brutal-sm',
  },
  {
    on: 'bg-pastel-green text-ink-on-accent',
    hover: 'hover:bg-pastel-green hover:text-ink-on-accent hover:shadow-brutal-sm',
  },
  {
    on: 'bg-accent-orange text-ink-on-accent',
    hover: 'hover:bg-accent-orange hover:text-ink-on-accent hover:shadow-brutal-sm',
  },
];
