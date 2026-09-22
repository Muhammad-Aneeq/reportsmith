/**
 * Light / dark, with the reader's system preference as the starting point.
 *
 * Stamps `data-theme` on the root element, which tokens.css treats as winning over the
 * media query in both directions — so a reader who prefers dark can still choose light for
 * a screenshot, and the choice survives a reload.
 */

import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

function initial(): Theme {
  const stored = localStorage.getItem('rs-theme');
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initial);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('rs-theme', theme);
  }, [theme]);

  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      className="rs-icon-btn"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      <span aria-hidden>{theme === 'dark' ? '☀' : '☾'}</span>
    </button>
  );
}
