import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { NAV_ACCENTS, navItems, newChatAction } from './navItems';

/**
 * Navigation dock — the desktop rail.
 *
 * `lg` and up only: a slim icon-only rail pinned to the left edge, centered
 * vertically. Below `lg` the MobileNav drawer takes over, because a left rail is
 * out of reach on a phone and an unlabelled glyph says nothing to a first-time
 * visitor. The boundary is pure CSS so there is no viewport query in JS to drift
 * out of sync with the stylesheet, and no state to lose when a phone rotates.
 *
 * The first item is the `newChatAction` button: it has no URL, so it is a
 * button that asks the shell to start a fresh conversation. Everything after it
 * is a real `<Link>`, so middle-click and "open in new tab" work the way they do
 * anywhere else on the web. The link is the only thing that navigates: an extra
 * onClick that also navigated would push a second history entry and make the
 * back button need two presses. App derives the active item from the URL, so the
 * links need no per-item callback — only the action button does.
 *
 * Selection splits the two chat states apart: a bare `/chat` is a fresh
 * conversation, so the New chat button shows as selected, while `/chat/<id>` is
 * a saved conversation, so the Chat link does. Without that split, hitting New
 * chat would light up Chat and read as if Chat had been pressed.
 */
export default function Dock({ active, freshChat, onNewChat }) {
  const NewChatIcon = newChatAction.icon;
  const newChatActive = freshChat === true;
  return (
    <motion.nav
      aria-label="Main navigation"
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.05 }}
      className="fixed left-4 top-1/2 z-40 hidden -translate-y-1/2 flex-col items-center gap-2 rounded border-[3px] border-nb-line bg-paper-surface p-2 shadow-brutal lg:flex"
    >
      {/* New chat — the action that starts a fresh conversation. */}
      <motion.div
        key={newChatAction.key}
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 320, damping: 22, delay: 0.08 }}
      >
        <div className="nb-tooltip-host relative flex">
          <button
            type="button"
            onClick={onNewChat}
            aria-label={newChatAction.name}
            aria-current={newChatActive ? 'page' : undefined}
            className={`${ACTION_CLASS} ${
              newChatActive
                ? `${NAV_ACCENTS[0].on} shadow-brutal-sm -translate-y-[2px]`
                : `${IDLE_CLASS} ${NAV_ACCENTS[0].hover}`
            }`}
          >
            <NewChatIcon
              className={`h-5 w-5 ${newChatActive ? 'text-ink-on-accent' : ''}`}
              aria-hidden="true"
              strokeWidth={newChatActive ? 3 : 2}
            />
            <span className="sr-only">{newChatAction.name}</span>
          </button>
          <span className="nb-tooltip" role="presentation">
            {newChatAction.name}
          </span>
        </div>
      </motion.div>

      {/* View links — start counting after the action for the stagger and accents. */}
      {navItems.map((item, index) => {
        const Icon = item.icon;
        // On a bare `/chat` the New chat button already shows as selected, so
        // the Chat link stands down rather than lighting up alongside it.
        const isActive = active === item.key && !(item.key === 'chat' && newChatActive);
        const accent = NAV_ACCENTS[(index + 1) % NAV_ACCENTS.length];
        return (
          <motion.div
            key={item.key}
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: 'spring', stiffness: 320, damping: 22, delay: 0.08 + (index + 1) * 0.04 }}
          >
            {/* relative + the tooltip's absolute placement: the plate anchors to
                this wrapper so it can sit outside the link's own box. */}
            <div className="nb-tooltip-host relative flex">
              <Link
                to={item.path}
                aria-current={isActive ? 'page' : undefined}
                aria-label={item.name}
                className={`${ACTION_CLASS} ${
                  isActive ? `${accent.on} shadow-brutal-sm -translate-y-[2px]` : `${IDLE_CLASS} ${accent.hover}`
                }`}
              >
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
                  on hover and :focus-visible; touch devices suppress it via the
                  media query in index.css. */}
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

// A single plate size for every rail item, so the column stays even.
const ACTION_CLASS =
  'flex h-11 w-11 items-center justify-center rounded border-[3px] border-nb-line transition-all duration-100';

// Idle ground shared by every unselected item; the accent comes from the hover
// pair so each icon flashes its own colour.
const IDLE_CLASS = 'bg-paper-surface text-ink';
