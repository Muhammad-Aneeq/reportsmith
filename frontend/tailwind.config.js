/**
 * Tailwind, scoped to layout.
 *
 * The aurora tokens are exposed to the theme so a screen can reach for `text-aurora-dim`
 * without redefining a colour — but the components themselves use the CSS variables directly,
 * because they have to keep working if this config is ever replaced (spec 00 A2's packaging
 * goal).
 *
 * `preflight` stays on: it is Tailwind's reset, and `tokens.css` is imported after base so the
 * element styles here win where they overlap.
 */

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        aurora: {
          navy: 'var(--aurora-navy)',
          'navy-deep': 'var(--aurora-navy-deep)',
          emerald: 'var(--aurora-emerald)',
          amber: 'var(--aurora-amber)',
          rose: 'var(--aurora-rose)',
          text: 'var(--aurora-text)',
          dim: 'var(--aurora-text-dim)',
          faint: 'var(--aurora-text-faint)',
        },
      },
      fontFamily: {
        display: ['var(--aurora-font-display)'],
        body: ['var(--aurora-font-body)'],
        mono: ['var(--aurora-font-mono)'],
      },
      borderRadius: {
        aurora: 'var(--aurora-radius)',
      },
    },
  },
  plugins: [],
};
