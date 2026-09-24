document.addEventListener('DOMContentLoaded', () => {
  const chartEl = document.getElementById('kana-chart');
  const flashEl = document.getElementById('flash-mode');
  const modeBtns = document.querySelectorAll('.mode-btn');

  modeBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      modeBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (btn.dataset.mode === 'chart') {
        chartEl.hidden = false;
        flashEl.hidden = true;
      } else {
        chartEl.hidden = true;
        flashEl.hidden = false;
      }
    });
  });

  // tap-to-reveal on chart tiles
  document.querySelectorAll('.kana-tile').forEach(tile => {
    tile.addEventListener('click', () => {
      const romajiEl = tile.querySelector('.kana-romaji');
      romajiEl.classList.toggle('emphasized');
      if (window.Sfx) Sfx.tap();
    });
  });

  // Flashcards
  const basicKana = (window.KANA_DATA || []).filter(k => k.type === 'basic');
  let idx = 0;
  let showingRomaji = false;
  const front = document.getElementById('flash-front');
  const progress = document.getElementById('flash-progress');
  const card = document.getElementById('flashcard');

  function render() {
    if (!basicKana.length) return;
    const item = basicKana[idx];
    front.textContent = showingRomaji ? item.romaji : item.char;
    front.classList.toggle('showing-romaji', showingRomaji);
    progress.textContent = `${idx + 1} / ${basicKana.length}`;
  }

  if (card) {
    card.addEventListener('click', () => {
      showingRomaji = !showingRomaji;
      if (window.Sfx) Sfx.flip();
      render();
    });
    document.getElementById('flash-next').addEventListener('click', () => {
      idx = (idx + 1) % basicKana.length;
      showingRomaji = false;
      render();
    });
    document.getElementById('flash-prev').addEventListener('click', () => {
      idx = (idx - 1 + basicKana.length) % basicKana.length;
      showingRomaji = false;
      render();
    });
    render();
  }
});
