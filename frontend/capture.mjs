/**
 * Capture the six screens, headless, against a live API.
 *
 * This is the UI verification the Chrome extension could not do on the build machine
 * (BLOCKERS B6), and it produces the README screenshot at the same time. It is not a
 * screenshot script with assertions bolted on — it **fails** if a screen renders empty, if
 * an error state appears where it should not, or if a claim the README makes about a screen
 * is not on that screen. A screenshot of a broken page is worse than no screenshot.
 *
 *   node capture.mjs                 # both themes, into ../docs/screenshots/
 *   node capture.mjs --theme dark
 */

import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, '..', 'docs', 'screenshots');
const BASE = process.env.CAPTURE_BASE ?? 'http://localhost:5173';

const themeArg = process.argv.indexOf('--theme');
const THEMES = themeArg > -1 ? [process.argv[themeArg + 1]] : ['dark', 'light'];

/** Each screen, and what must be true on it for the capture to count. */
const SCREENS = [
  {
    name: 'templates',
    path: '/templates',
    expect: ['Monthly Management Pack', 'Section preview', 'narrative'],
    forbid: ['Could not load'],
  },
  {
    name: 'pack-run',
    path: '/run',
    expect: ['Run a period', 'Gaps', 'blocks issuance', 'Headline figures'],
    forbid: ['Could not load'],
  },
  {
    // Deliberately deep-linked to a NARRATIVE section. The first section of the pack is a
    // KPI grid, and a screenshot of that shows none of what this screen is for — the AI
    // draft, the diff, the figure chips, the verified badge.
    name: 'review',
    path: '/review/3',
    click: 'Performance commentary',
    expect: ['Review', 'Sections', 'approve', 'figures verified', 'Figures this section'],
    forbid: ['Could not load'],
  },
  {
    // Pack 3 is mid-review, so this shows the CHECKLIST with its blocking gap — the
    // governance argument. Packs 1 and 2 are issued and would show the archive panel.
    name: 'signoff',
    path: '/signoff/3',
    expect: ['Sign-off', 'Checklist', 'Gaps resolved or waived', 'Sign off and issue'],
    forbid: ['Could not load'],
  },
  {
    name: 'archive',
    path: '/archive',
    expect: ['Archive'],
    forbid: ['Could not load'],
  },
  {
    name: 'month-diff',
    path: '/diff',
    expect: ['Month diff'],
    forbid: ['Could not load'],
  },
  {
    name: 'aurora',
    path: '/aurora',
    expect: ['aurora', 'Surfaces', 'Indicators', 'Evidence'],
    forbid: ['Could not load'],
  },
];

async function settle(page) {
  // TanStack Query renders a skeleton first. Waiting for networkidle alone races it, so
  // wait for the loading role to disappear as well — otherwise every screenshot is of a
  // shimmer, which is exactly the "screenshot of nothing" this script exists to prevent.
  await page.waitForLoadState('networkidle');
  await page
    .waitForFunction(() => !document.querySelector('[role="status"]'), { timeout: 8000 })
    .catch(() => {});
  await page.waitForTimeout(350);
}

const problems = [];

async function capture(browser, theme) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: theme,
    reducedMotion: 'reduce', // deterministic frames; no half-finished transitions
  });
  const page = await context.newPage();

  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`[${theme}] console error: ${m.text().slice(0, 160)}`);
  });
  page.on('pageerror', (e) => problems.push(`[${theme}] page error: ${String(e).slice(0, 160)}`));

  for (const screen of SCREENS) {
    await page.goto(`${BASE}${screen.path}`, { waitUntil: 'domcontentloaded' });
    // The toggle stamps data-theme, which wins over the media query in both directions.
    await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
    await settle(page);

    if (screen.click) {
      await page.getByRole('button', { name: screen.click }).first().click();
      await settle(page);
    }

    const text = await page.locator('#main').innerText();

    for (const needle of screen.expect) {
      if (!text.toLowerCase().includes(needle.toLowerCase())) {
        problems.push(`[${theme}] ${screen.name}: expected to find ${JSON.stringify(needle)}`);
      }
    }
    for (const needle of screen.forbid) {
      if (text.includes(needle)) {
        problems.push(`[${theme}] ${screen.name}: shows ${JSON.stringify(needle)}`);
      }
    }
    if (text.trim().length < 120) {
      problems.push(`[${theme}] ${screen.name}: rendered almost nothing (${text.trim().length} chars)`);
    }

    // A page that scrolls sideways is broken on a laptop, and it is the single easiest
    // responsive failure to ship without noticing.
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );
    if (overflows) problems.push(`[${theme}] ${screen.name}: the page scrolls horizontally`);

    await page.screenshot({
      path: join(OUT, `${screen.name}-${theme}.png`),
      fullPage: true,
    });
    process.stdout.write(`  ${theme.padEnd(5)} ${screen.name}\n`);
  }

  // The README's hero shot: the Review screen, which carries the governance argument.
  if (theme === 'dark') {
    await page.goto(`${BASE}/review/3`, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
    await settle(page);
    await page.getByRole('button', { name: 'Performance commentary' }).first().click();
    await settle(page);
    await page.screenshot({ path: join(HERE, '..', 'docs', 'screenshot-review.png') });
    process.stdout.write('  dark  screenshot-review.png (README hero)\n');
  }

  // Narrow viewport: the responsive claim in PLAN D-019 is "down to a 1280px laptop".
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(`${BASE}/review/3`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  const narrowOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  if (narrowOverflow) problems.push(`[${theme}] review at 1280px scrolls horizontally`);

  await context.close();
}

const browser = await chromium.launch();
await mkdir(OUT, { recursive: true });
try {
  for (const theme of THEMES) await capture(browser, theme);
} finally {
  await browser.close();
}

if (problems.length) {
  console.error('\nCAPTURE FAILED — the screens did not render what they claim:');
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}
console.log(`\nOK — ${SCREENS.length} screens × ${THEMES.length} theme(s), no console errors, no overflow.`);
