import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { navItems, newChatAction } from './navItems';

// Rotate accent grounds so no two adjacent dock items share a colour — the
// bento "no two neighbours match" rule applied to navigation. These are solid
// accents, not pastels: the label sits on the ground, so the ground has to
// carry body text at AA in both themes.
//
// Each entry pairs the *selected* ground with the ground it previews on hover,
// so every icon flashes its own colour rather than one shared highlight.
// The pairs are written out in full instead of interpolated ("hover:" + accent)
// because Tailwind's scanner only emits classes it can see verbatim.
const ACCENTS = [
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

// The New chat action takes the first accent; the four view links follow, so
// neighbours still never match.
const IDLE_CLASS = 'bg-paper-surface text-ink';
const NEW_CHAT_ACCENT = ACCENTS[0];

const ACTION_CLASS =
  'flex h-11 w-11 items-center justify-center rounded border-[3px] border-nb-line transition-all duration-100 lg:h-11 lg:w-11';

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
 * The first item is the `newChatAction` button: it has no URL, so it is a
 * button that asks the shell to start a fresh conversation. Everything after
 * it is a real `<Link>`, so middle-click and "open in new tab" work the way
 * they do anywhere else on the web. The link is the only thing that navigates:
 * an extra onClick that also navigated would push a second history entry and
 * make the back button need two presses. App derives the active item from the
 * URL, so the links need no per-item callback — only the action button does.
 *
 * Selection splits the two chat states apart: a bare `/chat` is a fresh
 * conversation, so the New chat button shows as selected, while `/chat/<id>`
 * is a saved conversation, so the Chat link does. Without that split, hitting
 * New chat would light up Chat and read as if Chat had been pressed.
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
      className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-around gap-1 border-t-[3px] border-nb-line bg-paper-surface px-2 pt-1.5 pb-[calc(0.5rem+env(safe-area-inset-bottom))] lg:inset-x-auto lg:bottom-auto lg:left-4 lg:top-1/2 lg:-translate-y-1/2 lg:flex-col lg:items-center lg:gap-2 lg:rounded lg:border-[3px] lg:border-nb-line lg:shadow-brutal lg:p-2"
    >
      {/* New chat — the action that starts a fresh conversation. */}
      <motion.div
        key={newChatAction.key}
        className="flex flex-1 justify-center lg:flex-none"
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
                ? `${NEW_CHAT_ACCENT.on} shadow-brutal-sm -translate-y-[2px]`
                : `${IDLE_CLASS} ${NEW_CHAT_ACCENT.hover}`
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
        const accent = ACCENTS[(index + 1) % ACCENTS.length];
        return (
          <motion.div
            key={item.key}
            className="flex flex-1 justify-center lg:flex-none"
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
