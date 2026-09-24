document.addEventListener('DOMContentLoaded', () => {
  const panels = {
    intro: document.getElementById('fc-intro'),
    run: document.getElementById('fc-run'),
    done: document.getElementById('fc-done'),
  };
  function show(name) {
    Object.entries(panels).forEach(([k, el]) => { el.hidden = k !== name; });
  }

  let deck = 'kanji', level = 'mixed', count = 20;
  let cards = [], idx = 0, knew = 0, flipped = false;

  function wire(selector, attr, setter) {
    document.querySelectorAll(selector).forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll(selector).forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        setter(btn.dataset[attr]);
      });
    });
  }
  wire('#deck-options .mode-sel', 'deck', v => deck = v);
  wire('#fc-level-options .level-btn', 'level', v => level = v);
  wire('#fc-count-options .count-btn', 'count', v => count = parseInt(v, 10));

  const face = document.getElementById('fc-face');
  const cardEl = document.getElementById('fc-card');

  // Cards can hold anything from a single kanji to a long compound word or
  // an English phrase ("credit card", "to be interested in", …). A fixed
  // font-size overflows the card for the longer ones, so we shrink the
  // font to fit based on the longest line of the text we're about to show.
  // The *maximum* size still comes from CSS (--fc-front-max / --fc-back-max)
  // so the mobile breakpoint controls the ceiling; this just scales down.
  function maxSizeFor(varName, fallback) {
    const raw = getComputedStyle(cardEl).getPropertyValue(varName);
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : fallback;
  }

  function fitFont(el, text, maxSize) {
    const longest = String(text).split('\n').reduce((m, l) => Math.max(m, l.length), 1);
    let factor = 1;
    if (longest > 2) factor = 0.78;
    if (longest > 4) factor = 0.6;
    if (longest > 6) factor = 0.46;
    if (longest > 9) factor = 0.34;
    if (longest > 13) factor = 0.26;
    if (longest > 20) factor = 0.2;
    const size = Math.max(12, Math.round(maxSize * factor));
    el.style.fontSize = size + 'px';
  }

  function render() {
    const c = cards[idx];
    flipped = false;
    face.classList.remove('showing-romaji');
    face.textContent = c.front;
    fitFont(face, c.front, maxSizeFor('--fc-front-max', 76));
    document.getElementById('fc-progress').textContent = `${idx + 1} / ${cards.length}`;
  }

  cardEl.addEventListener('click', () => {
    const c = cards[idx];
    flipped = !flipped;
    if (window.Sfx) Sfx.flip();
    if (flipped) {
      const backText = c.sub ? `${c.back}\n${c.sub}` : c.back;
      face.textContent = backText;
      face.classList.add('showing-romaji');
      fitFont(face, backText, maxSizeFor('--fc-back-max', 36));
    } else {
      face.textContent = c.front;
      face.classList.remove('showing-romaji');
      fitFont(face, c.front, maxSizeFor('--fc-front-max', 76));
    }
  });

  function advance(gotIt) {
    if (gotIt) {
      knew++;
      markProgress(deck, cards[idx].front);
    }
    if (window.Sfx) { gotIt ? Sfx.correct() : Sfx.fail(); }
    if (idx < cards.length - 1) { idx++; render(); }
    else {
      document.getElementById('fc-score').textContent =
        `You knew ${knew} of ${cards.length}.`;
      show('done');
      if (window.Sfx) Sfx.complete();
      markStreakActive();
    }
  }

  function markProgress(deckName, front) {
    // Fire-and-forget: a failed save here shouldn't interrupt the deck.
    fetch('/api/progress/mark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deck: deckName, front }),
    }).catch(() => {});
  }
  document.getElementById('fc-knew').addEventListener('click', () => advance(true));
  document.getElementById('fc-again').addEventListener('click', () => advance(false));
  document.getElementById('fc-restart').addEventListener('click', () => show('intro'));

  document.getElementById('fc-start').addEventListener('click', async () => {
    const res = await fetch(`/api/flashcards?deck=${deck}&difficulty=${level}&count=${count}`);
    const data = await res.json();
    cards = data.cards || [];
    if (!cards.length) return;
    idx = 0; knew = 0;
    show('run');
    render();
  });
});
