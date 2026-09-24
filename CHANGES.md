# What changed

Your nine items, plus the themes, mapped to the files that implement
them. Everything was smoke-tested against a local `python app.py` run
(all routes 200, feedback API verified end to end, all JS syntax-checked).

---

### 1 & 2 — page pans sideways / nav should scroll on its own

`static/css/style.css`

Your diagnosis was right, and the specific cause is a flexbox default:
flex items get `min-width: auto`, so `.site-nav` refused to shrink below
the combined width of its ten links and pushed the whole document wider
than the screen. The hero text and the flashcard's "Didn't know" button
were casualties of the same thing.

- `.site-nav` now has `min-width: 0` (lets it shrink) plus
  `overflow-x: auto` (turns the overflow into its own scroll strip),
  `flex-wrap: nowrap`, and `white-space: nowrap` on the links.
- `overscroll-behavior-x: contain` stops a swipe on the nav from
  chaining out to the page.
- `html, body` get `overflow-x: hidden` and `max-width: 100%` as a
  backstop, so no future element can reintroduce the problem.
- Below 880px the nav drops to its own full-width row.
- `static/js/app.js` scrolls the active nav item into view on load,
  since the section you're on can now start off-screen.

### 3 — tighter tracing area + mistake detection

`static/js/trace.js` (new), `static/css/style.css`

- The stage **is** the character box now: a square whose guide glyph is
  measured with `TextMetrics` and scaled to fill 80% of it, so there's
  no dead margin to draw in. It carries a 田-style centring guide like a
  genkō-yōshi practice square.
- Checking compares your ink against the target on a 64×64 grid, scoring
  **coverage** (how much of the character you traced) and **spill** (how
  much ink landed outside it). Both must pass — see "How stroke checking
  works" in the README for the thresholds and how to tune them.
- Three misses on the same character → the square shakes and the phone
  vibrates. Needed `VIBRATE` in `android/app/src/main/AndroidManifest.xml`.

### 4 — same tracing for hiragana and katakana

`templates/write.html`, `static/js/write.js`

One reusable component mounted three times. Hiragana and Katakana panels
now have **Tracing / Keyboard** sub-tabs (tracing first), each with a
scrollable character picker. Kanji keeps its search box.

### 5 — "Write" → "Writing Practice"

`templates/base.html` (nav), `templates/index.html` (homepage card),
`templates/write.html` (page title and `<title>`), `app.py`.

`/writing-practice` added as a route; `/write` kept registered so old
bookmarks and any cached service-worker entry still resolve.

### 6 — sound effects

`static/js/sfx.js` (new)

Synthesised at runtime with the Web Audio API rather than loaded from
files — worth it here because the APK has no network, so there's nothing
to miss and nothing added to the download. Tones come from the yo scale
(よな抜き音階). Wired into: practice quiz answers, story quiz answers,
flashcard flip, kana chart flip, writing-check pass/fail, round complete,
and key taps. Mute toggle in the header menu.

### 7 — verb and everyday popups misfit on mobile

`static/css/style.css`

Below 560px both modals become bottom sheets: full width, anchored to the
bottom edge, with a grab handle. Height is based on `100dvh` (the
*visible* viewport) so a collapsing address bar can't push the card
off-screen — that's what `86vh` was getting wrong. Safe-area padding for
notched phones, and the conjugation table is `table-layout: fixed` so it
stops forcing the card wider than the screen.

### 8 — About Us

`templates/about.html` (new), `/about` in `app.py`

Aryan Raj · Software Engineer · Aryanrajr868@gmail.com. Linked from the
footer, the header settings menu, and a homepage card.

### 9 — Feedback

`templates/feedback.html`, `static/js/feedback.js` (new),
`/feedback` + `/api/feedback` in `app.py`

Topic, 1–5 rating, message, optional name. Saved to
`data/feedback.json` on the device; there's no server to send to, so
"Send by email instead" hands the note to the phone's mail app — the
only path off-device, and the person's choice.

### Themes + dark mode

`static/css/style.css`, `static/js/theme.js` (new), `templates/base.html`

Five palettes plus Match System: **Washi** 和紙 (default), **Sakura** 桜,
**Matcha** 抹茶, **Sumi** 墨 (dark), **Yozakura** 夜桜 (dark). Every
hardcoded colour in the stylesheet became a token, so a theme is just a
different `data-theme` value on `<html>`. An inline script in `<head>`
applies the saved theme before the first paint, so navigation never
flashes the light palette. `values-night/themes.xml` added on the Android
side for the same reason at launch.

---

## Things I fixed along the way

- **`templates/base.html`** had `class="{{ 'active' if ... }}nav-cta"`,
  which concatenates to `activenav-cta` — so the Practice button lost its
  pill styling on its own page. Now `class="nav-cta {{ 'active' if ... }}"`.
- **The APK could silently miss your edits.** It ships its own copy of
  `app.py`/`templates/`/`static/`/`data/` under
  `android/app/src/main/python/kotoba_app/`, and the build workflow only
  triggered on `android/**`. Added `sync_android.py`, wired it into CI as
  a build step, and widened the trigger paths.
- **Webfonts blocked first paint in the APK.** `base.html` loads three
  Google Fonts. With no network, that request stalls rendering until it
  times out. It's now loaded non-blockingly
  (`media="print" onload="this.media='all'"`). See
  `static/fonts/README.md` for making the app fully self-contained.
- **`mailto:` in a WebView** just shows an error page, so
  `MainActivity.kt` now overrides URL loading to hand non-local schemes
  to the system. Also added the Android 11+ `<queries>` entry so the mail
  app is resolvable, and `mediaPlaybackRequiresUserGesture = false` so
  the first sound of a session isn't swallowed.
