import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { navItems } from './navItems';

// Rotate accent grounds so no two adjacent dock items share a colour — the
// bento "no two neighbours match" rule applied to navigation. These are solid
// accents, not pastels: the label sits on the ground, so the ground has to
// carry body text at AA in both themes.
const ACCENTS = [
  'bg-accent-yellow',
  'bg-accent-cyan',
  'bg-accent-magenta',
  'bg-pastel-green',
  'bg-accent-orange',
  'bg-pastel-purple',
];

/**
 * Navigation dock — the app's only navigation, so it has to work on every
 * screen size.
 *
 * Desktop (>= lg): a slim icon-only rail pinned to the left edge, centered
 * vertically.
 * Mobile (< lg): the same items become a thumb-reachable bottom bar, because a
 * left rail is out of reach on a phone and the palette trigger in the TopNav
 * reads as a search box, not as navigation.
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
      className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-around gap-1 border-t-[3px] border-nb-line bg-paper-surface px-2 pt-1.5 pb-[calc(0.5rem+env(safe-area-inset-bottom))] lg:inset-x-auto lg:bottom-auto lg:left-4 lg:top-1/2 lg:-translate-y-1/2 lg:flex-col lg:items-center lg:gap-2 lg:rounded lg:border-[3px] lg:border-nb-line lg:shadow-brutal lg:p-2"
    >
      {navItems.map((item, index) => {
        const Icon = item.icon;
        const isActive = active === item.key;
        const accent = ACCENTS[index % ACCENTS.length];
        return (
          <motion.div
            key={item.key}
            className="flex flex-1 justify-center lg:flex-none"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 22, delay: 0.08 + index * 0.04 }}
          >
            {/* relative + the tooltip's absolute placement: the plate anchors to
                this wrapper so it can sit outside the link's own box. */}
            <div className="nb-tooltip-host relative flex">
              <Link
                to={item.path}
                aria-current={isActive ? 'page' : undefined}
                aria-label={item.name}
                className={`flex h-11 w-11 items-center justify-center rounded border-[3px] border-nb-line transition-all duration-100 lg:h-11 lg:w-11 ${
                  isActive
                    ? `${accent} text-ink-on-accent shadow-brutal-sm -translate-y-[2px]`
                    : 'bg-paper-surface text-ink hover:bg-accent-yellow hover:text-ink-on-accent hover:shadow-brutal-sm'
                }`}
              >
                {/* Shape change carries the state too: the active icon thickens
                    to strokeWidth 3, so the current page is legible without
                    relying on tint. */}
                {/* Inactive icons inherit the link's colour rather than setting
                    their own, so the yellow hover ground actually carries the ink
                    with it. A pinned `text-ink-secondary` left the icon at
                    1.20:1 against yellow in dark theme. */}
                <Icon
                  className={`h-5 w-5 ${isActive ? 'text-ink-on-accent' : ''}`}
                  aria-hidden="true"
                  strokeWidth={isActive ? 3 : 2}
                />
                <span className="sr-only">{item.name}</span>
              </Link>
              {/* Neo-Brutalism hover plate: a hard-bordered black chip with a
                  square offset arrow, replacing the native `title` bubble the
                  OS draws in its own grey rounded style. Real DOM, not a CSS
                  ::after, so the label stays in the accessibility tree. Shows
                  on hover and :focus-visible; the mobile bottom bar suppresses
                  it via the media query in index.css. */}
              <span className="nb-tooltip" role="presentation">
                {item.name}
              </span>
            </div>
          </motion.div>
        );
      })}
    </motion.nav>
  );
}
