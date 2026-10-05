import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { navItems } from './navItems';

/**
 * Floating glass dock — the app's only navigation, so it has to work on every
 * screen size.
 *
 * Desktop (>= lg): a slim icon-only rail pinned to the left edge, centered
 * vertically, with a spring entrance per item.
 * Mobile (< lg): the same items become a thumb-reachable bottom bar, because a
 * left rail is out of reach on a phone and the palette trigger in the TopNav
 * reads as a search box, not as navigation.
 *
 * Tooltips carry the labels; the active view glows with the gradient. Items are
 * real anchors, so middle-click and "open in new tab" work the way they do
 * anywhere else on the web. The link is the only thing that navigates: an extra
 * onClick that also navigated would push a second history entry and make the
 * back button need two presses. App derives the active item from the URL, so
 * no callback is needed at all.
 */
export default function Dock({ active }) {
  return (
    <motion.nav
      aria-label="Main navigation"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.05 }}
      className="glass-strong fixed inset-x-0 bottom-0 z-40 flex items-center justify-around gap-1 border-t border-glass-border px-2 pt-1.5 pb-[calc(0.375rem+env(safe-area-inset-bottom))] shadow-float lg:inset-x-auto lg:bottom-auto lg:left-4 lg:top-1/2 lg:-translate-y-1/2 lg:flex-col lg:items-center lg:gap-2 lg:rounded-2xl lg:border lg:p-2 lg:shadow-float"
    >
      {navItems.map((item, index) => {
        const Icon = item.icon;
        const isActive = active === item.key;
        return (
          <motion.div
            key={item.key}
            className="flex flex-1 justify-center lg:flex-none"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 22, delay: 0.08 + index * 0.04 }}
            whileTap={{ scale: 0.94 }}
          >
            <Link
              to={item.path}
              aria-current={isActive ? 'page' : undefined}
              aria-label={item.name}
              title={item.name}
              className={`relative flex h-11 w-11 items-center justify-center rounded-xl transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 lg:h-10 lg:w-10 ${
                isActive
                  ? 'bg-bioluminescent text-white shadow-glow-violet'
                  : 'text-ink-muted hover:bg-paper-200 hover:text-ink'
              }`}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden="true" />
              {isActive && (
                <motion.span
                  layoutId="dock-active-dot"
                  className="absolute -bottom-1 h-1.5 w-1.5 rounded-full bg-bioluminescent shadow-glow-violet lg:-left-2.5 lg:-bottom-auto"
                />
              )}
            </Link>
          </motion.div>
        );
      })}
    </motion.nav>
  );
}