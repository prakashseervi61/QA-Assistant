import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { navItems } from './navItems';

/**
 * Floating glass dock — the spatial replacement for the sidebar. A slim
 * icon-only rail pinned to the left edge, centered vertically, with a
 * spring entrance per item. Tooltips carry the labels; the active view
 * glows with the bioluminescent gradient. Desktop-only (< lg hides it;
 * mobile navigation lives in the ⌘K palette via TopNav).
 *
 * Items are real anchors, so middle-click and "open in new tab" work the way
 * they do anywhere else on the web. The link is the only thing that navigates:
 * an extra onClick that also navigated would push a second history entry and
 * make the back button need two presses. App derives the active item from the
 * URL, so no callback is needed at all.
 */
export default function Dock({ active }) {
  return (
    <motion.nav
      aria-label="Main navigation"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.05 }}
      className="glass-strong fixed left-4 top-1/2 z-40 hidden -translate-y-1/2 flex-col items-center gap-2 rounded-2xl p-2 shadow-float lg:flex"
    >
      {navItems.map((item, index) => {
        const Icon = item.icon;
        const isActive = active === item.key;
        return (
          <motion.div
            key={item.key}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 22, delay: 0.08 + index * 0.04 }}
            whileHover={{ y: -2, scale: 1.06 }}
            whileTap={{ scale: 0.94 }}
          >
            <Link
              to={item.path}
              aria-current={isActive ? 'page' : undefined}
              aria-label={item.name}
              title={item.name}
              className={`relative flex h-10 w-10 items-center justify-center rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
                isActive
                  ? 'bg-bioluminescent text-white shadow-glow-violet'
                  : 'text-ink-muted hover:bg-paper-200 hover:text-ink'
              }`}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
              {isActive && (
                <motion.span
                  layoutId="dock-active-dot"
                  className="absolute -left-2.5 h-1.5 w-1.5 rounded-full bg-bioluminescent shadow-glow-violet"
                />
              )}
            </Link>
          </motion.div>
        );
      })}
    </motion.nav>
  );
}