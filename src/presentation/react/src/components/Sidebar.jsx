import { useEffect, useState } from 'react';
import {
  FiBookOpen,
  FiBookmark,
  FiClock,
  FiFolder,
  FiMenu,
  FiMessageSquare,
  FiMoon,
  FiSettings,
  FiSun,
  FiUsers,
  FiX,
} from 'react-icons/fi';
import { getTheme, setTheme } from '../theme';

const navItems = [
  { name: 'Chat', icon: FiMessageSquare, key: 'chat' },
  { name: 'Documents', icon: FiFolder, key: 'documents' },
  { name: 'Collections', icon: FiUsers, key: 'collections' },
  { name: 'Recent', icon: FiClock, key: 'recent' },
  { name: 'Bookmarks', icon: FiBookmark, key: 'bookmarks' },
  { name: 'Settings', icon: FiSettings, key: 'settings' },
];

/**
 * Global navigation sidebar, closable from a toggle inside the sidebar itself.
 * - On desktop (lg+) it is an in-flow column: width 256px when open, a narrow
 *   64px rail when collapsed — the toggle stays in the same spot in both.
 * - On smaller screens it becomes a slide-over drawer; when closed a floating
 *   hamburger keeps it reachable.
 */
export default function Sidebar({ active, onNavigate, open, onToggle, onClose }) {
  const [isDesktop, setIsDesktop] = useState(
    () => window.matchMedia('(min-width: 1024px)').matches
  );
  const [isDark, setIsDark] = useState(() => getTheme() === 'dark');

  function toggleTheme() {
    const next = isDark ? 'light' : 'dark';
    setIsDark(next === 'dark');
    setTheme(next);
  }

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    const handler = event => setIsDesktop(event.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, onClose]);

  const isRail = isDesktop && !open;

  /** Shared renderer for nav buttons (used both in the list and in the pinned Settings area). */
  function renderNavButton(item) {
    const Icon = item.icon;
    const isActive = active === item.key;
    return (
      <button
        key={item.key}
        type="button"
        onClick={() => onNavigate(item.key)}
        aria-current={isActive ? 'page' : undefined}
        title={isRail ? item.name : undefined}
        className={`relative flex w-full items-center rounded-lg text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
          isRail ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
        } ${
          isActive
            ? 'bg-stone-800 font-medium text-white shadow-sm'
            : 'text-stone-300 hover:bg-stone-800/60 hover:text-white'
        }`}
      >
        <Icon
          className={`h-5 w-5 shrink-0 transition-colors ${
            isActive ? 'text-brand-400' : 'text-stone-400'
          }`}
        />
        {!isRail && <span>{item.name}</span>}
      </button>
    );
  }

  /** Theme toggle in the same visual language as the nav buttons. */
  function renderThemeToggle() {
    const label = isDark ? 'Dark theme' : 'Light theme';
    const ThemeIcon = isDark ? FiMoon : FiSun;
    return (
      <button
        key="theme-toggle"
        type="button"
        onClick={toggleTheme}
        aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
        title={isRail ? label : undefined}
        className={`relative flex w-full items-center rounded-lg text-sm transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
          isRail ? 'justify-center px-0 py-2.5' : 'gap-3 px-3 py-2.5'
        } text-stone-300 hover:bg-stone-800/60 hover:text-white`}
      >
        <ThemeIcon className="h-5 w-5 shrink-0 text-stone-400" />
        {!isRail && <span>{isDark ? 'Dark' : 'Light'}</span>}
      </button>
    );
  }

  return (
    <>
      {/* Floating hamburger on mobile when the drawer is closed */}
      {!isDesktop && !open && (
        <button
          type="button"
          onClick={onToggle}
          aria-label="Open navigation menu"
          className="fixed left-4 top-4 z-50 rounded-lg bg-slate-900 p-2 text-white shadow-subtle transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        >
          <FiMenu className="h-5 w-5" />
        </button>
      )}

      <aside
        aria-label="Main navigation"
        style={isDesktop ? { width: isRail ? 64 : 256 } : undefined}
        className={
          isDesktop
            ? 'flex flex-col border-r border-[#292524] bg-[#181614] p-4 transition-[width] duration-200 ease-in-out'
            : `fixed inset-y-0 left-0 z-50 flex w-64 transform flex-col border-r border-[#292524] bg-[#181614] p-4 transition-transform duration-200 ease-in-out ${
                open ? 'translate-x-0 visible' : '-translate-x-full invisible'
              }`
        }
      >
        {/* Brand row — the toggle sits to the right of the brand name */}
        <div className="flex items-center justify-between border-b border-[#292524] pb-5">
          {!isRail && (
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white shadow-subtle">
                <FiBookOpen className="h-5 w-5" />
              </div>
              <div>
                <p className="whitespace-nowrap text-[15px] font-medium tracking-tight text-white">
                  Marginalia
                </p>
                <p className="whitespace-nowrap text-xs font-normal text-stone-400">
                  Notes on your documents
                </p>
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={onToggle}
            aria-label={open ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={open}
            className={`rounded-md p-1.5 text-stone-400 transition-colors hover:bg-stone-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
              isRail ? 'ml-0' : 'ml-auto'
            }`}
          >
            {open ? <FiX className="h-5 w-5" /> : <FiMenu className="h-5 w-5" />}
          </button>
        </div>

        {/* Navigation — icons stay visible when collapsed to the rail */}
        {(isDesktop || open) && (
          <nav className="flex-1 space-y-1 overflow-y-auto pt-4">
            {navItems
              .filter(item => item.key !== 'settings')
              .map(item => renderNavButton(item))}
          </nav>
        )}

        {/* Settings pinned to the bottom of the sidebar */}
        {(isDesktop || open) && (
          <div className="mt-auto space-y-1 border-t border-[#292524] pt-4">
            {renderThemeToggle()}
            {renderNavButton(navItems.find(item => item.key === 'settings'))}
          </div>
        )}
      </aside>
    </>
  );
}