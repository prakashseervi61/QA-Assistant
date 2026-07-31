import {
  FiBookmark,
  FiClock,
  FiFolder,
  FiHardDrive,
  FiMessageSquare,
  FiSettings,
  FiUsers,
  FiX,
} from 'react-icons/fi';

const navItems = [
  { name: 'Documents', icon: FiFolder, key: 'documents' },
  { name: 'Collections', icon: FiUsers, key: 'collections' },
  { name: 'Recent', icon: FiClock, key: 'recent' },
  { name: 'Bookmarks', icon: FiBookmark, key: 'bookmarks' },
  { name: 'Settings', icon: FiSettings, key: 'settings' },
];

/**
 * Global navigation sidebar.
 * - On desktop (lg+) it is a static column.
 * - On smaller screens it becomes a slide-over drawer toggled from the header.
 */
export default function Sidebar({ active, onNavigate, open, onClose }) {
  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-64 transform flex-col bg-slate-900 p-4 transition-transform duration-200 ease-in-out lg:static lg:z-auto lg:translate-x-0 ${
        open ? 'translate-x-0' : '-translate-x-full'
      }`}
      aria-label="Main navigation"
    >
      {/* Brand */}
      <div className="flex items-center justify-between pb-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white">
            <FiMessageSquare className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight text-white">QA Assistant</p>
            <p className="text-xs text-slate-400">Document Q&amp;A</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close navigation menu"
          className="rounded-md p-1.5 text-slate-400 transition-colors hover:bg-slate-800 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 lg:hidden"
        >
          <FiX className="h-5 w-5" />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto">
        {navItems.map(item => {
          const Icon = item.icon;
          const isActive = active === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onNavigate(item.key)}
              aria-current={isActive ? 'page' : undefined}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 ${
                isActive
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span>{item.name}</span>
            </button>
          );
        })}
      </nav>

      {/* Workspace footer */}
      <div className="mt-4 rounded-xl border border-slate-800 bg-slate-800/50 p-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-600/20 text-xs font-semibold text-brand-300">
            LW
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-white">Local Workspace</p>
            <p className="flex items-center gap-1 text-xs text-slate-400">
              <FiHardDrive className="h-3 w-3" />
              1.2 GB of 5 GB used
            </p>
          </div>
        </div>
        <div
          className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-700"
          role="progressbar"
          aria-valuenow={24}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Workspace storage used"
        >
          <div className="h-full w-1/4 rounded-full bg-brand-500" />
        </div>
      </div>
    </aside>
  );
}
