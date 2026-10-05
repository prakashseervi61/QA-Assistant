// ponytail: autoprefixer was a no-op pass here — package.json declared no
// browserslist key, and the stylesheet uses no property that needs a prefix
// beyond the hand-written ::-webkit-scrollbar selectors and
// -webkit-font-smoothing, which are already written out.
export default {
  plugins: {
    tailwindcss: {},
  },
}
