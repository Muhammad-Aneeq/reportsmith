/**
 * Record the demo — by driving the real product, not by animating a mockup.
 *
 * `docs/DEMO_SCRIPT.md` is the shot list a person would follow with a screen recorder. This
 * executes the same sequence against the live app and captures it to webm, so the repo ships
 * an actual clip of the software working rather than a promise that it does.
 *
 * What it is: a silent screen recording, correctly paced, of the governance flow end to end.
 * What it is not: narrated, or cut to music. The launch video still wants a voice over the
 * top — but the footage underneath it is this, and it is reproducible with one command.
 *
 *   node record-demo.mjs                      # → docs/demo.webm
 *   CAPTURE_BASE=http://localhost:5176 node record-demo.mjs
 *
 * Requires the seeded three-pack state (see `make demo-state`).
 */

import { chromium } from 'playwright';
import { mkdir, readdir, rename, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const DOCS = join(HERE, '..', 'docs');
const TMP = join(HERE, '.video-tmp');
const BASE = process.env.CAPTURE_BASE ?? 'http://localhost:5173';

// Deliberate, watchable pacing. A demo that flicks between screens faster than a viewer can
// read is a demo nobody learns anything from.
const BEAT = 900;
const READ = 2200;

const steps = [];
function narrate(text) {
  // Printed, not burned into the video. These are the lines a voiceover would say, in order,
  // so whoever records the audio has the timing already worked out.
  steps.push(text);
  process.stdout.write(`  ${text}\n`);
}

async function settle(page) {
  await page.waitForLoadState('networkidle');
  await page
    .waitForFunction(() => !document.querySelector('[role="status"]'), { timeout: 8000 })
    .catch(() => {});
  await page.waitForTimeout(400);
}

/** Scroll an element into the middle of the frame and pause on it. */
async function look(page, locator, ms = READ) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  await page.waitForTimeout(ms);
}

await rm(TMP, { recursive: true, force: true });
await mkdir(TMP, { recursive: true });
await mkdir(DOCS, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  colorScheme: 'dark',
  recordVideo: { dir: TMP, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();

try {
  // ---------------------------------------------------------------- templates --
  narrate('Define the pack once: four section types, a closed binding grammar, tone rules.');
  await page.goto(`${BASE}/templates`, { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'dark'));
  await settle(page);
  await look(page, page.getByText('Section preview'), BEAT);
  await page.locator('.rs-yaml').evaluate((el) => el.scrollTo({ top: 260, behavior: 'smooth' }));
  await page.waitForTimeout(READ);
  await page.locator('.rs-yaml').evaluate((el) => el.scrollTo({ top: 900, behavior: 'smooth' }));
  await page.waitForTimeout(READ);

  // ----------------------------------------------------------------- pack run --
  narrate('Run a period. Bindings resolve — and what did not bind is reported, not dropped.');
  await page.goto(`${BASE}/run`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await look(page, page.getByRole('heading', { name: 'Gaps' }), READ + 600);

  // ------------------------------------------------------------------- review --
  narrate('Every number the model wrote is checked against the figures it was given.');
  await page.goto(`${BASE}/review/3`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await page.getByRole('button', { name: 'Performance commentary' }).first().click();
  await settle(page);
  await look(page, page.getByText('figures verified').first(), READ);

  narrate('That chip list is its entire numeric universe. Anything else does not survive.');
  await look(page, page.getByText('Figures this section could cite'), READ + 400);

  narrate('Edit it, and the AI draft stays beside the change — word by word.');
  await page.getByRole('button', { name: 'Edit narrative' }).click();
  await page.waitForTimeout(BEAT);
  const editor = page.locator('#editor');
  await editor.click();
  await editor.press('End');
  await editor.type(' Margin compression continued into the month.', { delay: 38 });
  await page.waitForTimeout(BEAT);
  await page.getByRole('button', { name: 'Save edit' }).click();
  await settle(page);
  await look(page, page.getByRole('heading', { name: 'AI draft vs current' }), READ + 800);

  // ------------------------------------------------------------------ signoff --
  narrate('It refuses to issue. Eleven sections unapproved, three gaps unresolved.');
  await page.goto(`${BASE}/signoff/3`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await look(page, page.getByRole('heading', { name: 'Checklist' }), READ);

  narrate('Approve everything — and it still refuses, because the gaps are still open.');
  await page.goto(`${BASE}/review/3`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  const sections = page.locator('.rs-sectionlist-item');
  const count = await sections.count();
  for (let i = 0; i < count; i += 1) {
    await sections.nth(i).click();
    await page.waitForTimeout(120);
    const approve = page.getByRole('button', { name: 'Approve', exact: true });
    if (await approve.count()) {
      await approve.first().click();
      await page.waitForTimeout(160);
    }
  }
  await page.goto(`${BASE}/signoff/3`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await look(page, page.getByRole('heading', { name: 'Checklist' }), READ);

  narrate('A waiver needs a reason, and the reason is recorded under the signer’s name.');
  const waivers = page.locator('.rs-waiver');
  const waiverCount = (await waivers.count()) - 1; // the last one is the signer field
  for (let i = 0; i < waiverCount; i += 1) {
    await waivers.nth(i).click();
    await waivers.nth(i).type('No segment data this period; accepted by the controller.', {
      delay: 14,
    });
    await page.waitForTimeout(240);
  }
  await page.waitForTimeout(BEAT);

  narrate('Now it signs — and archives the document, the data snapshot and a hash.');
  await page.getByRole('button', { name: 'Sign off and issue' }).click();
  await settle(page);
  await page.waitForTimeout(READ);

  // ------------------------------------------------------------------ archive --
  narrate('The archive can be checked by anyone holding the directory.');
  await page.goto(`${BASE}/archive`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  const verify = page.getByRole('button', { name: 'Verify now' }).first();
  if (await verify.count()) {
    await verify.click();
    await page.waitForTimeout(READ);
  }

  // --------------------------------------------------------------- month diff --
  narrate('Same template, next month. Identical structure, changed numbers.');
  await page.goto(`${BASE}/diff`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await page.waitForTimeout(READ + 1200);
  // One second in light, because both themes are designed.
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'light'));
  await page.waitForTimeout(1600);
} finally {
  await context.close(); // the video is only flushed on close
  await browser.close();
}

const [file] = (await readdir(TMP)).filter((f) => f.endsWith('.webm'));
if (!file) {
  console.error('No video was produced.');
  process.exit(1);
}
await rename(join(TMP, file), join(DOCS, 'demo.webm'));
await rm(TMP, { recursive: true, force: true });

console.log(`\nWrote docs/demo.webm — ${steps.length} beats.`);
console.log('Voiceover lines, in order, are printed above; timing is already paced for them.');
