// Things to play with on the landing page:
//  1. the mood grid: tap a creature and a spark flies to the guide, which changes into that mood
//  2. the island cards: they open into a window with a live island (states, go dark, more, switching clients)
//     and the nudge story (drift, how far did you get, what's next), the way the app does it
(() => {
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const lerp = (a, b, t) => a + (b - a) * t;
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const SOFT = 'linear(0,.018,.064,.129,.204,.285,.366,.445,.52,.589,.652,.709,.759,.802,.84,.872,.899,.921,.94,.955,.968,.977,.985,.991,.996,.999,1.001,1.003,1.004,1.005,1.005,1.005,1.005,1.005,1.004,1.004,1.003,1.003,1.003,1.002,1)';
  const creature = (mood = 'working', style = '') =>
    `<span class="mb" data-mood="${mood}" style="${style}"><span class="g-eyes"><span class="g-blink"><i></i><i></i></span></span><b class="g-z">z<small>z</small></b><span class="g-spk"></span></span>`;

  /* ================= 1. moods ================= */
  const MOODS = [['working', 'working'], ['lockedin', 'locked in'], ['sidequest', 'side quest'], ['away', 'away'], ['gonedark', 'gone dark'],
    ['unsure', 'not sure yet'], ['switched', 'switched client'], ['milestone', '₹1,000 milestone'], ['goal', 'daily goal hit']];
  const pic = $('#moods-pic');
  if (pic) {
    pic.innerHTML = `<div class="moods" role="group" aria-label="the creature's moods: tap one and the guide up top tries it on">${MOODS.map(([m, name], i) =>
      `<button type="button" class="mood" data-m="${m}" aria-pressed="false" style="--i:${i}">${creature(m)}<span class="ml">${name}</span></button>`).join('')}</div>
      <p class="moods-hint" aria-live="polite">tap one · the guide up top tries it on</p>`;
    const grid = $('.moods', pic), hint = $('.moods-hint', pic);
    let worn = 'working', spark = null;
    grid.addEventListener('click', e => {
      const b = e.target.closest('.mood');
      if (!b || !window.lowkeyGuide) return;
      const m = b.dataset.m === worn && worn !== 'working' ? 'working' : b.dataset.m;  // tap the one it's wearing: back to working
      worn = m;
      $$('.mood', grid).forEach(x => x.setAttribute('aria-pressed', String(x.dataset.m === m && m !== 'working')));
      const name = MOODS.find(x => x[0] === m)[1];
      hint.textContent = m === 'working' ? 'back to working · tap another' : `the guide is ${name} now · tap it again to undo`;
      const from = b.querySelector('.mb');
      if (!REDUCED) from.animate([{transform: 'translateY(0) scale(1)'}, {transform: 'translateY(2px) scale(1.15,.85)'}, {transform: 'translateY(-12px) scale(.92,1.1)'},
        {transform: 'translateY(0) scale(1.05,.95)'}, {transform: 'none'}], {duration: 620, easing: 'cubic-bezier(.2,0,0,1)'});
      spark?.cancel();  // rapid taps: the last one wins
      spark = fly(from, m, () => window.lowkeyGuide.mood(m));
    });
    // the grid's eyes follow you too
    let raf = 0, px = 0, py = 0;
    addEventListener('pointermove', e => {
      px = e.clientX; py = e.clientY;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const g = grid.getBoundingClientRect();
        if (g.bottom < -100 || g.top > innerHeight + 100) return;
        $$('.mb', grid).forEach(c => {
          const r = c.getBoundingClientRect(), dx = px - (r.left + r.width / 2), dy = py - (r.top + r.height / 2), d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 200);
          c.querySelector('.g-eyes').style.transform = `translate(${dx / d * k * 4}px, ${dy / d * k * 3}px)`;
        });
      });
    }, {passive: true});
  }

  function fly(fromEl, mood, done) {  // a spark in the mood's colour arcs from the creature to the guide (and chases it if it moves)
    if (REDUCED) { done(); return {cancel() {}}; }
    const r = fromEl.getBoundingClientRect(), from = {x: r.left + r.width / 2, y: r.top + r.height / 2};
    const el = document.createElement('div');
    el.className = 'spark';
    el.innerHTML = `<span class="mb" data-mood="${mood}"></span>` + '<i></i>'.repeat(5);
    document.body.append(el);
    const head = el.firstElementChild, trail = $$('i', el), pts = trail.map(() => ({...from}));
    trail.forEach(t => t.style.background = getComputedStyle(head).getPropertyValue('--c2'));
    const t0 = performance.now(), dur = 760;
    let live = true, pos = {...from};
    const step = now => {
      if (!live) return;
      const to = window.lowkeyGuide.point(), t = Math.min(1, (now - t0) / dur), e = ease(t), u = 1 - e;
      const c = {x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 140};
      pos = {x: u * u * from.x + 2 * u * e * c.x + e * e * to.x, y: u * u * from.y + 2 * u * e * c.y + e * e * to.y};
      const s = 1 - Math.sin(t * Math.PI) * -.35;
      head.style.transform = `translate(${pos.x - 9}px, ${pos.y - 9}px) scale(${s})`;
      pts.forEach((p, i) => { const lead = i ? pts[i - 1] : pos; p.x = lerp(p.x, lead.x, .45); p.y = lerp(p.y, lead.y, .45);
        trail[i].style.transform = `translate(${p.x - 4}px, ${p.y - 4}px) scale(${1 - i * .16})`; });
      if (t < 1) return requestAnimationFrame(step);
      live = false;
      const ring = document.createElement('b');
      ring.className = 'spark-ring';
      ring.style.cssText = `left:${pos.x}px;top:${pos.y}px;border-color:${getComputedStyle(head).getPropertyValue('--c2')}`;
      document.body.append(ring);
      ring.animate([{transform: 'translate(-50%,-50%) scale(.2)', opacity: 1}, {transform: 'translate(-50%,-50%) scale(2.4)', opacity: 0}], {duration: 520, easing: 'cubic-bezier(.2,0,0,1)'}).onfinish = () => ring.remove();
      el.remove();
      done();
    };
    requestAnimationFrame(step);
    return {cancel() { if (!live) return; live = false; el.animate([{opacity: 1}, {opacity: 0}], {duration: 160}).onfinish = () => el.remove(); }};
  }

  /* ================= 3. log what it couldn't see ================= */
  // Your day as blocks; the hatched gaps are time lowkey didn't see. Click one (or drag across part of it), say what it
  // was, and it's billed like any other session. Plain keyword matching stands in for the app's parser here.
  const DAY0 = 9 * 60, DAY1 = 16 * 60, SPAN = DAY1 - DAY0;
  const RATES = {'Acme Studio': 1200, 'Chai & Co': 900, 'Nimbus Labs': 1500};
  const HUES = {'Acme Studio': '#B8FF3B', 'Chai & Co': '#FF7AD9', 'Nimbus Labs': '#7AA2FF', 'side quest': '#d9d4c7'};
  const HINTS = [[/nimbus|api|postman|invoice/i, 'Nimbus Labs'], [/acme|login|oauth|figma/i, 'Acme Studio'], [/chai|shopify|banner|masala/i, 'Chai & Co']];
  const hm = m => `${((Math.floor(m / 60) + 11) % 12) + 1}:${String(m % 60).padStart(2, '0')}${m < 720 ? 'a' : 'p'}`;
  const money = n => '₹' + Math.round(n).toLocaleString('en-IN');
  const logPic = $('#log-pic');
  if (logPic) {
    const seen = [[555, 645, 'Chai & Co'], [675, 780, 'Acme Studio'], [825, 930, 'Nimbus Labs']];  // 9:15–10:45, 11:15–1:00, 1:45–3:30
    let logged = [], total = 5390, sel = null, pending = null, undoT;
    logPic.innerHTML = `<div class="lg">
      <div class="lg-top"><span class="lg-k">friday · your day</span><span class="lg-total">today <b>₹5,390</b></span></div>
      <div class="lg-bar" role="group" aria-label="your day, with gaps you can log"></div>
      <div class="lg-axis">${[9, 10, 11, 12, 13, 14, 15, 16].map(h => `<span style="left:${(h * 60 - DAY0) / SPAN * 100}%">${h > 12 ? h - 12 : h}${h < 12 ? 'a' : 'p'}</span>`).join('')}</div>
      <div class="lg-pop" hidden><div class="lg-span"></div>
        <input class="lg-in" type="text" maxlength="60" placeholder="what was it?" aria-label="what was it?">
        <div class="lg-sug"><button type="button">call with nimbus</button><button type="button">acme standup</button><button type="button">sketching the chai banner</button></div>
        <div class="lg-row"><span class="lg-who"></span><span class="lg-worth"></span><button type="button" class="lg-go">log it</button></div></div>
      <p class="lg-hint" aria-live="polite">click a gap · or drag across part of one</p></div>`;
    const bar = $('.lg-bar', logPic), pop = $('.lg-pop', logPic), inp = $('.lg-in', logPic), hint = $('.lg-hint', logPic), totalEl = $('.lg-total b', logPic);
    const pct = m => (m - DAY0) / SPAN * 100;
    const gaps = () => {  // free time between what was seen and what you've logged, 5 minutes or more
      const taken = [...seen, ...logged].map(x => [x[0], x[1]]).sort((a, b) => a[0] - b[0]), out = [];
      let t = DAY0;
      taken.forEach(([a, b]) => { if (a - t >= 5) out.push([t, a]); t = Math.max(t, b); });
      if (DAY1 - t >= 5) out.push([t, DAY1]);
      return out;
    };
    function draw(fresh) {
      bar.innerHTML = seen.map(([a, b, c]) => `<i class="lg-blk" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%;background:${HUES[c]}"></i>`).join('') +
        logged.map((x, i) => `<button type="button" class="lg-blk lg-mine${x === fresh ? ' fresh' : ''}" data-i="${i}" style="left:${pct(x[0])}%;width:${pct(x[1]) - pct(x[0])}%;--h:${HUES[x[2]]}" aria-label="${x[3]}, ${hm(x[0])} to ${hm(x[1])}, added by you · remove"></button>`).join('') +
        gaps().map(([a, b]) => `<button type="button" class="lg-gap" data-a="${a}" data-b="${b}" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%" aria-label="${b - a} minutes nobody saw, ${hm(a)} to ${hm(b)}: log it"><span>+${b - a}m</span></button>`).join('') +
        '<i class="lg-sel"></i>';
      if (!gaps().length) hint.innerHTML = 'every minute accounted for · <button type="button" class="lg-reset">start over</button>';
    }
    const roll = to => {  // the total counts up (or down) to its new value
      const from = total, t0 = performance.now();
      total = to;
      const step = now => { const t = Math.min(1, (now - t0) / 700); totalEl.textContent = money(from + (to - from) * ease(t)); if (t < 1) requestAnimationFrame(step); };
      REDUCED ? totalEl.textContent = money(to) : requestAnimationFrame(step);
      if (!REDUCED) totalEl.animate([{transform: 'scale(1)'}, {transform: 'scale(1.12)'}, {transform: 'scale(1)'}], {duration: 500, easing: 'cubic-bezier(.2,0,0,1)'});
    };
    const showSel = () => {
      const s = $('.lg-sel', bar);
      s.style.left = pct(sel[0]) + '%'; s.style.width = (pct(sel[1]) - pct(sel[0])) + '%';
      s.classList.add('on');
    };
    const guess = text => { for (const [re, c] of HINTS) if (re.test(text)) return c; return null; };
    function preview() {
      const c = guess(inp.value), mins = sel[1] - sel[0];
      $('.lg-span', pop).textContent = `${hm(sel[0])} – ${hm(sel[1])} · ${mins}m`;
      $('.lg-who', pop).innerHTML = c ? `<i style="background:${HUES[c]}"></i>${c}` : (inp.value.trim() ? '<i></i>side quest' : '<i></i>say what it was');
      $('.lg-worth', pop).textContent = c ? money(mins / 60 * RATES[c]) : inp.value.trim() ? 'off the invoice' : '';
      $('.lg-go', pop).disabled = !inp.value.trim();
    }
    function openPop() {
      showSel();
      pop.hidden = false;
      const r = bar.getBoundingClientRect(), w = Math.min(320, logPic.clientWidth - 16), mid = r.left + r.width * (pct((sel[0] + sel[1]) / 2) / 100) - logPic.getBoundingClientRect().left;
      pop.style.width = w + 'px';
      pop.style.left = Math.max(8, Math.min(logPic.clientWidth - w - 8, mid - w / 2)) + 'px';
      pop.style.setProperty('--tail', (mid - parseFloat(pop.style.left)) + 'px');
      if (!REDUCED) pop.animate([{opacity: 0, transform: 'translateY(-6px) scale(.95)'}, {opacity: 1, transform: 'none'}], {duration: 320, easing: 'cubic-bezier(.2,0,0,1)'});
      inp.value = ''; preview();
      inp.focus({preventScroll: true});
    }
    const closePop = () => { pop.hidden = true; sel = null; $('.lg-sel', bar)?.classList.remove('on'); };
    function commit() {
      const text = inp.value.trim();
      if (!text || !sel) return;
      const c = guess(text) || 'side quest', entry = [sel[0], sel[1], c, text];
      logged.push(entry);
      const worth = c in RATES ? (sel[1] - sel[0]) / 60 * RATES[c] : 0, from = $('.lg-sel', bar).getBoundingClientRect();
      closePop();
      draw(entry);
      if (worth) roll(total + worth);
      capsule(from, worth ? `+${money(worth)}` : 'side quest', HUES[c]);
      clearTimeout(undoT);
      hint.innerHTML = `logged · ${text} <button type="button" class="lg-undo">undo</button>`;
      pending = entry;
      undoT = setTimeout(() => { pending = null; if (gaps().length) hint.textContent = 'logged blocks are dotted · click one to remove it'; }, 5000);
    }
    function remove(entry) {
      logged = logged.filter(x => x !== entry);
      if (entry[2] in RATES) roll(total - (entry[1] - entry[0]) / 60 * RATES[entry[2]]);
      draw();
      hint.textContent = 'removed · click a gap · or drag across part of one';
    }
    function capsule(rect, text, color) {  // what you logged flies home to the island, like changes do in the app
      if (REDUCED || !window.lowkeyGuide) return window.lowkeyGuide?.catch?.(color);
      const el = document.createElement('div');
      el.className = 'cap-fly';
      el.textContent = text;
      el.style.background = color;
      document.body.append(el);
      const from = {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2}, t0 = performance.now(), dur = 900;
      const step = now => {
        const to = window.lowkeyGuide.point(), t = Math.min(1, (now - t0) / dur), e = ease(t), u = 1 - e, c = {x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - 160};
        const x = u * u * from.x + 2 * u * e * c.x + e * e * to.x, y = u * u * from.y + 2 * u * e * c.y + e * e * to.y;
        el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${1 - e * .55})`;
        el.style.opacity = t > .85 ? String((1 - t) / .15) : '1';
        if (t < 1) return requestAnimationFrame(step);
        el.remove();
        window.lowkeyGuide.catch?.(color);
      };
      requestAnimationFrame(step);
    }

    // pick: click a gap for all of it, or drag across part of it (5-minute steps, never past the gap)
    let drag = null;
    const at = (e, g) => { const r = bar.getBoundingClientRect(), m = DAY0 + (e.clientX - r.left) / r.width * SPAN; return Math.max(g[0], Math.min(g[1], Math.round(m / 5) * 5)); };
    bar.addEventListener('pointerdown', e => {
      const g = e.target.closest('.lg-gap');
      if (!g) return;
      e.preventDefault();
      const gap = [+g.dataset.a, +g.dataset.b];
      drag = {gap, start: at(e, gap), moved: false};
      bar.setPointerCapture(e.pointerId);
    });
    bar.addEventListener('pointermove', e => {
      if (!drag) return;
      const m = at(e, drag.gap);
      if (Math.abs(m - drag.start) >= 5) { drag.moved = true; sel = [Math.min(m, drag.start), Math.max(m, drag.start)]; showSel(); }
    });
    bar.addEventListener('pointerup', () => {
      if (!drag) return;
      if (!drag.moved || !sel || sel[1] - sel[0] < 5) sel = [...drag.gap];
      drag = null;
      openPop();
    });
    bar.addEventListener('click', e => {
      const mine = e.target.closest('.lg-mine');
      if (mine) remove(logged[+mine.dataset.i]);
    });
    bar.addEventListener('keydown', e => {  // keyboard: Enter on a gap takes all of it
      const g = e.target.closest('.lg-gap');
      if (g && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); sel = [+g.dataset.a, +g.dataset.b]; openPop(); }
    });
    inp.addEventListener('input', preview);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') { e.stopPropagation(); closePop(); } });
    $('.lg-sug', pop).addEventListener('click', e => { const b = e.target.closest('button'); if (b) { inp.value = b.textContent; preview(); inp.focus(); } });
    $('.lg-go', pop).addEventListener('click', commit);
    logPic.addEventListener('click', e => {
      if (e.target.closest('.lg-undo') && pending) { clearTimeout(undoT); const p = pending; pending = null; remove(p); hint.textContent = 'undone · click a gap · or drag across part of one'; }
      if (e.target.closest('.lg-reset')) { logged = []; roll(5390); draw(); hint.textContent = 'click a gap · or drag across part of one'; }
    });
    document.addEventListener('pointerdown', e => { if (!pop.hidden && !e.target.closest('.lg-pop, .lg-bar')) closePop(); });
    draw();
  }

  /* ================= 2. windows with a live island ================= */
  const CLIENTS = {
    'Acme Studio': {c: ['#f2ffd0', '#B8FF3B', '#86c414'], money: '₹5,220', task: 'Fixed OAuth redirect bug on the login page, reviewed PR #42', glow: '184,255,59'},
    'Chai & Co': {c: ['#ffe3f6', '#FF7AD9', '#d6439c'], money: '₹5,220', task: 'Modified product card theme, previewed Masala Chai 250g', glow: '255,122,217'},
    'Nimbus Labs': {c: ['#e6eeff', '#7AA2FF', '#4467cf'], money: '₹5,220', task: 'Coded handlers.py and documented the Nimbus API v2', glow: '122,162,255'},
  };
  const paint = (mb, name) => { const c = CLIENTS[name].c; mb.style.setProperty('--c1', c[0]); mb.style.setProperty('--c2', c[1]); mb.style.setProperty('--c3', c[2]); };
  const WAVE = 'M0 40 C 30 18, 56 12, 82 32 S 128 44, 152 18 S 204 12, 230 24 S 286 18, 316 20 S 356 44, 378 32 S 428 12, 458 10';

  function islandHTML() {
    return `<div class="mi" data-s="lip">
      <i class="mi-lipglow"></i>
      <div class="mf" data-f="pill">${creature()}<b class="mi-nm">Acme Studio</b>
        <svg class="mi-sq" viewBox="0 0 54 24"><path d="M2 14 C 8 2, 14 2, 20 12 S 32 22, 38 10 S 48 4, 52 8" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>
        <span class="mi-tm"></span><span class="mi-mo">₹5,220</span></div>
      <div class="mf" data-f="open">
        <div class="mi-top">${creature()}<div><b class="mi-nm">Acme Studio</b><span class="mi-ses"><i></i>this session <span class="mi-tm"></span></span></div>
          <div class="mi-earn"><b>₹5,220</b><span>earned today</span></div></div>
        <div class="mi-task"></div>
        <svg class="mi-wave" viewBox="0 0 460 50" preserveAspectRatio="none"><path d="${WAVE}" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>
        <div class="mi-row"><div class="mi-a"><span class="mi-stat"><svg viewBox="0 0 40 40"><circle cx="20" cy="20" r="15" fill="none" stroke="#333" stroke-width="5"/><circle cx="20" cy="20" r="15" fill="none" stroke="currentColor" stroke-width="5" stroke-dasharray="66 100" transform="rotate(-90 20 20)"/></svg><b>4h 21m</b> today</span>
            <span class="mi-stat"><i class="mi-dot"></i><b>3</b> to review</span>
            <span class="mi-btns"><button type="button" data-a="dark" aria-label="go dark"><svg viewBox="0 0 26 26"><path d="M18 4a10 10 0 1 0 5 13A8 8 0 0 1 18 4z" fill="#fff"/></svg></button><button type="button" data-a="open" class="go" aria-label="open lowkey"><svg viewBox="0 0 26 26"><path d="M7 19L19 7M9 7h10v10" stroke="#111" stroke-width="3.2" fill="none" stroke-linecap="round"/></svg></button><button type="button" data-a="more" aria-label="more">•••</button></span></div>
          <div class="mi-b"><button type="button" data-a="notwork">not work</button><button type="button" data-a="pin">pin</button><button type="button" data-a="settings">settings</button><button type="button" data-a="less" aria-label="back">✕</button></div></div>
        <div class="mi-hint">hover a button and it tells you what it does</div>
      </div>
      <div class="mf" data-f="toast">${creature()}<span class="mi-msg"></span><button type="button" class="mi-undo" data-a="undo">undo</button><i class="mi-count"></i></div>
      <div class="mf" data-f="dark"><span class="mi-stars"></span>${creature('gonedark')}<span class="mi-msg">gone dark · <em>off the record</em></span><button type="button" data-a="resume" class="mi-sun">resume</button></div>
      <div class="mf" data-f="prompt"><div class="mi-ph">${creature('unsure')}<div><b class="mi-pt"></b><span class="mi-ps"></span></div></div><div class="mi-pa"></div></div>
    </div>`;
  }

  function Island(root, client = 'Acme Studio') {
    const el = $('.mi', root);
    let started = Date.now() - (1 * 3600 + 24 * 60 + 7) * 1000, s = 'lip', pinned = false, toastT, undoFn = null, dark = false;
    const api = {el, get state() { return s; }, get client() { return client; }, pinned: () => pinned};
    const set = (state, face = state) => {
      s = state; el.dataset.s = state;
      $$('.mf', el).forEach(f => f.classList.toggle('on', f.dataset.f === face));
      if (state !== 'open') el.classList.remove('more');
      root.dispatchEvent(new CustomEvent('island', {detail: state}));
    };
    const tick = () => {
      const t = Math.floor((Date.now() - started) / 1000), h = Math.floor(t / 3600), m = Math.floor(t / 60) % 60, sec = t % 60;
      $$('.mi-tm', el).forEach(x => x.textContent = `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`);
    };
    const who = () => {
      $$('.mi-nm', el).forEach(x => x.textContent = client);
      $$('.mf:not([data-f=dark]):not([data-f=prompt]) .mb', el).forEach(mb => paint(mb, client));
      el.style.setProperty('--cc', CLIENTS[client].c[1]);
      $('.mi-task', el).textContent = CLIENTS[client].task;
    };
    who(); tick();
    api.timer = setInterval(tick, 1000);
    api.set = set;
    api.rest = () => set(dark ? 'dark' : pinned ? 'pill' : 'lip', dark ? 'dark' : pinned ? 'pill' : 'lip');
    api.toast = (msg, {undo, ms = 2600, then} = {}) => {
      clearTimeout(toastT);
      $('[data-f=toast] .mi-msg', el).innerHTML = msg;
      undoFn = undo || null;
      el.classList.toggle('undoable', !!undo);
      set('toast');
      const bar = $('.mi-count', el);
      bar.getAnimations().forEach(a => a.cancel());
      if (undo && !REDUCED) bar.animate([{transform: 'scaleX(1)'}, {transform: 'scaleX(0)'}], {duration: ms, easing: 'linear'});
      toastT = setTimeout(() => { undoFn = null; then ? then() : api.rest(); }, ms);
      if (!REDUCED) $('[data-f=toast] .mb', el).animate([{transform: 'scale(.6) rotate(-20deg)'}, {transform: 'scale(1.1) rotate(4deg)'}, {transform: 'none'}], {duration: 520, easing: 'cubic-bezier(.2,0,0,1)'});
    };
    api.switchTo = name => {
      if (name === client) return;
      client = name; started = Date.now() - 1000; who(); tick();
      api.toast(`switched to <b style="color:var(--cc)">${name}</b>`);
      el.animate([{boxShadow: `0 0 0 0 rgba(${CLIENTS[name].glow},0)`}, {boxShadow: `0 10px 40px rgba(${CLIENTS[name].glow},.75)`}, {boxShadow: `0 0 0 0 rgba(${CLIENTS[name].glow},0)`}], {duration: 900});
    };
    api.prompt = (title, sub, actions, mood = 'unsure') => {
      clearTimeout(toastT);
      $('.mi-pt', el).textContent = title;
      $('.mi-ps', el).textContent = sub;
      $('[data-f=prompt] .mb', el).dataset.mood = mood;
      const pa = $('.mi-pa', el);
      pa.innerHTML = actions.map((a, i) => `<button type="button" class="${a.kind || ''}" data-i="${i}">${a.label}</button>`).join('');
      pa.style.setProperty('--n', actions.length);
      pa.onclick = e => { const b = e.target.closest('button'); b && actions[+b.dataset.i].on(); };
      set('prompt');
      if (!REDUCED) $$('button', pa).forEach((b, i) => b.animate([{opacity: 0, transform: 'translateY(8px) scale(.9)'}, {opacity: 1, transform: 'none'}], {duration: 420, delay: 140 + i * 50, easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards'}));
    };
    el.addEventListener('click', e => {
      const a = e.target.closest('[data-a]')?.dataset.a;
      if (!a) return;
      e.stopPropagation();
      if (a === 'more') el.classList.add('more');
      if (a === 'less') el.classList.remove('more');
      if (a === 'dark') { dark = true; set('dark'); }
      if (a === 'resume') { dark = false; api.toast('back on the clock'); }
      if (a === 'open') api.toast('this opens your dashboard · <a href="demo/">try it here</a>', {ms: 3400});
      if (a === 'pin') { pinned = !pinned; el.classList.toggle('pinned', pinned); api.toast(pinned ? 'pinned · it stays out' : 'unpinned · it tucks away'); }
      if (a === 'settings') api.toast('edge, taskbar and rest live in the island too');
      if (a === 'notwork') api.toast('moved to side quests · off the invoice', {undo: () => api.toast('undone · back on the invoice'), ms: 5000});
      if (a === 'undo' && undoFn) { const f = undoFn; undoFn = null; f(); }
    });
    // what each control does, in the line under the name (the app's Live Activity trick)
    const HINT = {dark: 'go dark · pause tracking, nothing gets saved', open: 'open lowkey · your dashboard', more: 'more · not work, pin, settings',
      notwork: 'not work · keeps this session off the invoice', pin: 'pin · keep the island out', settings: 'settings · where it lives', less: 'back'};
    el.addEventListener('pointerover', e => { const a = e.target.closest('[data-a]')?.dataset.a; if (HINT[a]) $('.mi-hint', el).textContent = HINT[a]; });
    const idle = matchMedia('(hover: hover)').matches ? 'hover a button and it tells you what it does' : 'tap a button to try it';
    $('.mi-hint', el).textContent = idle;
    el.addEventListener('pointerout', e => { if (e.target.closest('[data-a]')) $('.mi-hint', el).textContent = idle; });
    api.destroy = () => { clearInterval(api.timer); clearTimeout(toastT); };
    set('lip');
    return api;
  }

  // ---- window 1: the island's states ----
  function statesDemo(body) {
    body.innerHTML = `<div class="dsk"><div class="dsk-wall"></div>
        <div class="dsk-win code" style="left:4%;top:20%;width:58%;height:66%"><div class="dsk-bar"><b></b><b></b><b></b><span>login.tsx — acme-website</span></div>${'<i></i>'.repeat(7)}</div>
        <div class="dsk-win" style="left:46%;top:32%;width:50%;height:58%"><div class="dsk-bar"><b></b><b></b><b></b><span>github.com/acme-studio/acme-website/pull/42</span></div><p>OAuth redirect fix <span>#42</span></p>${'<i></i>'.repeat(3)}</div>
        ${islandHTML()}
        <div class="dsk-cap"><b></b><span></span></div></div>
      <div class="pw-ctl"><span class="pw-k">switch client</span>${Object.keys(CLIENTS).map(n => `<button type="button" class="chip-c" data-c="${n}" style="--cc:${CLIENTS[n].c[1]}"><i></i>${n}</button>`).join('')}
        <span class="pw-tip">hover the notch · keep hovering · try the buttons</span></div>`;
    const isl = Island(body);
    const CAP = {lip: ['tucked away', 'a glowing lip in your client\'s colour'], pill: ['hover', 'your client\'s creature, a live timer, ₹ today'],
      open: ['keep hovering', 'your last hour as a flow wave, and three buttons'], dark: ['gone dark', 'nothing is recorded until you resume'],
      toast: ['it tells you', 'every change, in one line']};
    const cap = $('.dsk-cap', body);
    body.addEventListener('island', e => { const c = CAP[e.detail]; if (c) { $('b', cap).textContent = c[0]; $('span', cap).textContent = c[1]; } });
    $('b', cap).textContent = CAP.lip[0]; $('span', cap).textContent = CAP.lip[1];
    // hover: lip → pill (120ms) → open (600ms); leave: back after 350ms. Touch: tap to step through.
    let t1, t2, t3;
    const el = isl.el, hoverable = matchMedia('(hover: hover)').matches;
    const grow = () => { clearTimeout(t3); if (isl.state === 'lip' || isl.state === 'pill') { t1 = setTimeout(() => isl.state === 'lip' && isl.set('pill'), 120); t2 = setTimeout(() => ['lip', 'pill'].includes(isl.state) && isl.set('open'), 720); } };
    const shrink = () => { clearTimeout(t1); clearTimeout(t2); t3 = setTimeout(() => { if (isl.state === 'open' || isl.state === 'pill') isl.rest(); }, 350); };
    if (hoverable) { el.addEventListener('pointerenter', grow); el.addEventListener('pointerleave', shrink); }
    el.addEventListener('click', e => { if (e.target.closest('[data-a]')) return; if (isl.state === 'lip') isl.set('pill'); else if (isl.state === 'pill') isl.set('open'); });
    body.addEventListener('click', e => { if (!hoverable && !e.target.closest('.mi') && ['pill', 'open'].includes(isl.state)) isl.rest(); });
    $('.pw-ctl', body).addEventListener('click', e => { const c = e.target.closest('[data-c]'); if (c) { isl.switchTo(c.dataset.c); mark(); } });
    const mark = () => $$('.chip-c', body).forEach(c => c.classList.toggle('on', c.dataset.c === isl.client));
    mark();
    setTimeout(() => isl.state === 'lip' && !el.matches(':hover') && isl.set('pill'), 900);  // a first nudge so you see it move
    setTimeout(() => isl.state === 'pill' && !el.matches(':hover') && isl.rest(), 2600);
    return () => { isl.destroy(); [t1, t2, t3].forEach(clearTimeout); };
  }

  // ---- window 2: a little desktop. Open apps from the Dock; the island reacts the way the app's would ----
  const ICON_D = {"youtube": "M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z", "postman": "M13.527.099C6.955-.744.942 3.9.099 10.473c-.843 6.572 3.8 12.584 10.373 13.428 6.573.843 12.587-3.801 13.428-10.374C24.744 6.955 20.101.943 13.527.099zm2.471 7.485a.855.855 0 0 0-.593.25l-4.453 4.453-.307-.307-.643-.643c4.389-4.376 5.18-4.418 5.996-3.753zm-4.863 4.861l4.44-4.44a.62.62 0 1 1 .847.903l-4.699 4.125-.588-.588zm.33.694l-1.1.238a.06.06 0 0 1-.067-.032.06.06 0 0 1 .01-.073l.645-.645.512.512zm-2.803-.459l1.172-1.172.879.878-1.979.426a.074.074 0 0 1-.085-.039.072.072 0 0 1 .013-.093zm-3.646 6.058a.076.076 0 0 1-.069-.083.077.077 0 0 1 .022-.046h.002l.946-.946 1.222 1.222-2.123-.147zm2.425-1.256a.228.228 0 0 0-.117.256l.203.865a.125.125 0 0 1-.211.117h-.003l-.934-.934-.294-.295 3.762-3.758 1.82-.393.874.874c-1.255 1.102-2.971 2.201-5.1 3.268zm5.279-3.428h-.002l-.839-.839 4.699-4.125a.952.952 0 0 0 .119-.127c-.148 1.345-2.029 3.245-3.977 5.091zm3.657-6.46l-.003-.002a1.822 1.822 0 0 1 2.459-2.684l-1.61 1.613a.119.119 0 0 0 0 .169l1.247 1.247a1.817 1.817 0 0 1-2.093-.343zm2.578 0a1.714 1.714 0 0 1-.271.218h-.001l-1.207-1.207 1.533-1.533c.661.72.637 1.832-.054 2.522zM18.855 6.05a.143.143 0 0 0-.053.157.416.416 0 0 1-.053.45.14.14 0 0 0 .023.197.141.141 0 0 0 .084.03.14.14 0 0 0 .106-.05.691.691 0 0 0 .087-.751.138.138 0 0 0-.194-.033z", "figma": "M15.852 8.981h-4.588V0h4.588c2.476 0 4.49 2.014 4.49 4.49s-2.014 4.491-4.49 4.491zM12.735 7.51h3.117c1.665 0 3.019-1.355 3.019-3.019s-1.355-3.019-3.019-3.019h-3.117V7.51zm0 1.471H8.148c-2.476 0-4.49-2.014-4.49-4.49S5.672 0 8.148 0h4.588v8.981zm-4.587-7.51c-1.665 0-3.019 1.355-3.019 3.019s1.354 3.02 3.019 3.02h3.117V1.471H8.148zm4.587 15.019H8.148c-2.476 0-4.49-2.014-4.49-4.49s2.014-4.49 4.49-4.49h4.588v8.98zM8.148 8.981c-1.665 0-3.019 1.355-3.019 3.019s1.355 3.019 3.019 3.019h3.117V8.981H8.148zM8.172 24c-2.489 0-4.515-2.014-4.515-4.49s2.014-4.49 4.49-4.49h4.588v4.441c0 2.503-2.047 4.539-4.563 4.539zm-.024-7.51a3.023 3.023 0 0 0-3.019 3.019c0 1.665 1.365 3.019 3.044 3.019 1.705 0 3.093-1.376 3.093-3.068v-2.97H8.148zm7.704 0h-.098c-2.476 0-4.49-2.014-4.49-4.49s2.014-4.49 4.49-4.49h.098c2.476 0 4.49 2.014 4.49 4.49s-2.014 4.49-4.49 4.49zm-.097-7.509c-1.665 0-3.019 1.355-3.019 3.019s1.355 3.019 3.019 3.019h.098c1.665 0 3.019-1.355 3.019-3.019s-1.355-3.019-3.019-3.019h-.098z", "whatsapp": "M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z", "spotify": "M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.301 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.72-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.299.421-1.02.599-1.559.3z"};  // Simple Icons (CC0): brand marks, drawn white on their brand colour
  const glyph = (d, fill = '#fff') => `<svg viewBox="0 0 24 24"><path d="${d}" fill="${fill}"/></svg>`;
  const APPS = {
    code: {name: 'VS Code', title: 'login.tsx — acme-website', bg: 'linear-gradient(160deg,#3ea6ff,#0065a9)', kind: 'client', client: 'Acme Studio',
      icon: '<svg viewBox="0 0 24 24"><path d="M17 3l4 2v14l-4 2-9-8.2L4 16l-2-1V9l2-1 4 3.2zm0 5.2L12.2 12 17 15.8z" fill="#fff"/></svg>'},
    figma: {name: 'Figma', title: 'Acme landing v3', bg: '#1e1e1e', kind: 'client', client: 'Acme Studio', icon: glyph(ICON_D.figma, '#fff')},
    postman: {name: 'Postman', title: 'POST /v2/invoices · nimbus-api', bg: '#FF6C37', kind: 'client', client: 'Nimbus Labs', icon: glyph(ICON_D.postman)},
    youtube: {name: 'YouTube', title: 'lofi hip hop radio · YouTube', bg: '#fff', kind: 'distraction', icon: glyph(ICON_D.youtube, '#FF0033')},
    whatsapp: {name: 'WhatsApp', title: 'WhatsApp · Mom', bg: '#25D366', kind: 'personal', icon: glyph(ICON_D.whatsapp)},
    spotify: {name: 'Spotify', title: 'Discover Weekly · Spotify', bg: '#121212', kind: 'music', icon: glyph(ICON_D.spotify, '#1ED760')},
  };
  const WIN = {  // what each app window shows
    code: `${'<i></i>'.repeat(8)}`,
    figma: `<div class="fg"><span style="--x:8%;--y:16%;--w:38%;--h:52%;background:#B8FF3B"></span><span style="--x:52%;--y:16%;--w:40%;--h:24%;background:#7AA2FF"></span><span style="--x:52%;--y:46%;--w:40%;--h:22%;background:#FF7AD9"></span><span style="--x:8%;--y:74%;--w:84%;--h:14%;background:#FFD23F"></span></div>`,
    postman: `<p><span class="verb">POST</span> /v2/invoices</p>${'<i></i>'.repeat(4)}`,
    youtube: `<div class="vid"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="56" fill="rgba(255,255,255,.18)"/><path d="M48 38 L86 60 L48 82 Z" fill="#fff"/></svg></div>`,
    whatsapp: `<div class="wa"><b>Mom</b><span class="in">did you eat?</span><span class="out">yes ma</span><span class="in">ok call later</span></div>`,
    spotify: `<div class="sp"><div class="art"></div><div><b>Discover Weekly</b><span>made for you</span><i></i><i></i><i></i></div></div>`,
  };
  const QUEUE0 = [{t: 'acme login redirect fix', c: 'Acme Studio', why: '₹1,200/h · due today'},
    {t: 'nimbus api docs', c: 'Nimbus Labs', why: '₹1,500/h · better paid'},
    {t: 'chai shopify banner', c: 'Chai & Co', why: '₹900/h · waiting longest'}];

  function nudgeDemo(body) {
    const QUEUE = QUEUE0.map(q => ({...q})), order = Object.keys(APPS);  // a fresh story every time the window opens
    body.innerHTML = `<div class="mac">
        <div class="mac-bar"><b class="mac-app">VS Code</b><span>File</span><span>Edit</span><span>View</span><span class="mac-r"><button type="button" class="mac-reset">↺ start over</button><span class="mac-clock">Fri 10:24</span></span></div>
        <div class="dsk"><div class="dsk-wall"></div>
          ${order.map((k, i) => `<div class="dsk-win app-${k}" data-app="${k}" style="--i:${i}"><div class="dsk-bar"><button type="button" class="tl" data-close="${k}" aria-label="close ${APPS[k].name}"></button><b></b><b></b><span>${APPS[k].title}</span></div>${WIN[k]}</div>`).join('')}
          <div class="dsk-now"><span>now</span><b></b><em></em></div>
          <div class="ff" aria-hidden="true"><svg viewBox="0 0 28 16"><path d="M1 1l11 7-11 7zM14 1l11 7-11 7z" fill="currentColor"/></svg><span>8 minutes later</span></div>
          <div class="dsk-cap"><b></b><span></span></div>
          <div class="dock-hint">open an app ↓</div>
          <div class="dock" role="toolbar" aria-label="Dock">${order.map(k => `<button type="button" class="dk" data-app="${k}" aria-label="open ${APPS[k].name}" style="background:${APPS[k].bg}"><span class="dk-tip">${APPS[k].name}</span>${APPS[k].icon}<i class="dk-run"></i></button>`).join('')}
            <span class="dk-sep"></span><button type="button" class="dk me" data-me aria-label="lowkey"><span class="dk-tip">lowkey</span>${creature()}</button></div>
        </div>
        ${islandHTML()}
      </div>
      <p class="pw-note">a simulation of the app's island on a made-up Mac · nothing here watches you</p>`;
    const mac = $('.mac', body), dsk = $('.dsk', body), cap = $('.dsk-cap', body), dock = $('.dock', body);
    const isl = Island(mac), timers = [];
    let now = 0, front = null, z = 10, minutes = 10 * 60 + 24, waiting = null, open = new Set();
    const later = (f, ms) => timers.push(setTimeout(f, ms));
    const caption = (b, s) => { $('b', cap).textContent = b; $('span', cap).textContent = s; };
    const clock = () => { $('.mac-clock', body).textContent = `Fri ${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`; };
    const intent = () => { const it = QUEUE[now]; $('.dsk-now b', body).textContent = it ? it.t : 'all clear'; $('.dsk-now em', body).textContent = it ? it.c : 'nothing lined up'; };

    function bring(k, fromDock) {  // open (zoom out of the Dock icon) or bring to front
      const w = $(`.dsk-win[data-app=${k}]`, body), icon = $(`.dk[data-app=${k}]`, body);
      w.style.zIndex = ++z;
      $('.mac-app', body).textContent = APPS[k].name;
      if (!open.has(k)) {
        open.add(k);
        icon.classList.add('running');
        w.classList.add('in');
        if (!REDUCED && fromDock) {
          const a = icon.getBoundingClientRect(), b = w.getBoundingClientRect();
          w.animate([{transform: `translate(${a.left + a.width / 2 - (b.left + b.width / 2)}px, ${a.top - b.top}px) scale(.08)`, opacity: .4},
            {transform: 'none', opacity: 1}], {duration: 520, easing: SOFT});
        }
      }
      if (front !== k) { front = k; react(k); }
    }
    function quit(k) {
      const w = $(`.dsk-win[data-app=${k}]`, body);
      open.delete(k);
      $(`.dk[data-app=${k}]`, body).classList.remove('running');
      w.classList.remove('in');
      if (front === k) {
        front = null;
        const next = [...open].sort((a, b) => +$(`.dsk-win[data-app=${b}]`, body).style.zIndex - +$(`.dsk-win[data-app=${a}]`, body).style.zIndex)[0];
        if (next) bring(next); else $('.mac-app', body).textContent = 'Finder';
      }
    }

    // what lowkey makes of the window in front (the app reads window titles; here the apps stand in for them)
    function react(k) {
      timers.splice(0).forEach(clearTimeout);
      $('.ff', body).classList.remove('go');
      const app = APPS[k], it = QUEUE[now];
      if (app.kind === 'client' && it && app.client === it.c) {
        if (waiting || isl.state === 'prompt') { waiting = null; $('[data-f=toast] .mb', isl.el).dataset.mood = 'goal'; isl.toast(`back on ${it.t}`); caption('back on it', 'the nudge is gone the moment you are'); }
        else { if (isl.client !== app.client) isl.switchTo(app.client); else isl.set('pill'); caption(`${app.name} · ${it.c}`, `"${app.title}" matches ${it.c}'s hints: you're on it`); }
        return;
      }
      if (app.kind === 'client') {  // another client's window: you've moved on
        waiting = 'ask';
        caption(`you opened ${app.name}`, `that's ${app.client}, not ${it ? it.c : 'what you said'}`);
        later(() => ask(app.client), 900);
        return;
      }
      if (app.kind === 'distraction') {
        caption('YouTube, for a minute…', 'research is fine · only real distractions count');
        later(() => { $('.ff', body).classList.add('go'); minutes += 8; clock(); }, 700);
        later(() => {
          $('.ff', body).classList.remove('go');
          if (!it) return;
          waiting = 'nudge';
          caption('drifted? a nudge', 'at most three an hour, never over a fullscreen movie');
          isl.prompt('8 min on YouTube', `back to ${it.t}?`, [
            {label: 'switch', on: () => ask(null)},
            {label: 'later', on: () => { waiting = null; isl.toast('ok · I won\'t nag'); caption('later counts too', 'an ignored nudge just means later'); }},
            {label: 'back on it', kind: 'go', on: () => { const back = order.find(x => APPS[x].client === it.c); bring(back, true); }},
          ], 'unsure');
        }, 2300);
        return;
      }
      if (app.kind === 'personal') { isl.toast('side quest · stays off the invoice'); caption('a side quest', 'personal time never reaches an invoice · no scolding'); return; }
      isl.toast('music doesn\'t count against you'); caption('Spotify in the background', 'neutral: it doesn\'t change who you\'re working for');
    }
    function ask(movedTo) {
      const it = QUEUE[now];
      if (!it) return;
      waiting = 'ask';
      caption('moved on? one tap', 'how far you got, in your words, not a guess');
      isl.prompt('how far did you get?', movedTo ? `${it.t} · you've moved on to ${movedTo}` : `${it.t} · it keeps its place in line`,
        ['just started', 'halfway', 'almost', 'done'].map((l, i) => ({label: l, kind: i === 3 ? 'go' : '', on: () => {
          const finished = i === 3;
          if (finished) QUEUE.push(QUEUE.splice(now, 1)[0]); else QUEUE.push(QUEUE.splice(now, 1)[0]);  // back in line either way; done goes last
          if (finished) QUEUE.at(-1).done = true;
          now = 0;
          $('[data-f=toast] .mb', isl.el).dataset.mood = finished ? 'milestone' : 'working';
          isl.toast(finished ? `done · nice, that took ${24 + 28}m` : `saved · ${l}`, {ms: 1600, then: () => next(movedTo)});
        }})), 'switched');
    }
    function next(movedTo) {
      const pick = QUEUE.findIndex(q => !q.done && (!movedTo || q.c === movedTo));
      const n = pick >= 0 ? pick : QUEUE.findIndex(q => !q.done);
      if (n < 0) { waiting = null; isl.toast('all clear · nothing lined up'); return; }
      const it = QUEUE[n];
      caption('then, what\'s next', 'with the reason: due soon, better paid, waiting longest');
      isl.prompt(`next up: ${it.t}`, it.why, [
        {label: 'later', on: () => { waiting = null; isl.toast('it keeps its place in line'); }},
        {label: 'start it', kind: 'blue', on: () => {
          QUEUE.unshift(QUEUE.splice(n, 1)[0]); now = 0; waiting = null; intent();
          isl.switchTo(it.c);
          caption('on it', `the timer starts, in ${it.c}'s colour`);
          const app = order.find(x => APPS[x].client === it.c);
          if (app && front !== app) later(() => bring(app, true), 900);
        }}], 'switched');
    }

    // the Dock: magnifies under the pointer, bounces on launch
    const dks = $$('.dk', dock);
    dock.addEventListener('pointermove', e => {
      if (REDUCED || e.pointerType !== 'mouse') return;
      dks.forEach(d => { const r = d.getBoundingClientRect(), dist = Math.abs(e.clientX - (r.left + r.width / 2)), k = Math.max(0, 1 - dist / 120);
        d.style.setProperty('--m', (1 + k * .5).toFixed(3)); });
    });
    dock.addEventListener('pointerleave', () => dks.forEach(d => d.style.setProperty('--m', 1)));
    dock.addEventListener('click', e => {
      const d = e.target.closest('.dk');
      if (!d) return;
      $('.dock-hint', body).classList.add('gone');
      if (!REDUCED) d.animate([{translate: '0 0'}, {translate: '0 -16px'}, {translate: '0 0'}, {translate: '0 -8px'}, {translate: '0 0'}], {duration: 700, easing: 'ease-out'});
      if (d.hasAttribute('data-me')) { $('[data-f=toast] .mb', isl.el).dataset.mood = 'goal'; isl.toast('that\'s me · I live in the notch'); return; }
      bring(d.dataset.app, true);
    });
    body.addEventListener('click', e => {
      const c = e.target.closest('[data-close]');
      if (c) { e.stopPropagation(); quit(c.dataset.close); return; }
      const w = e.target.closest('.dsk-win.in');
      if (w && !e.target.closest('.mi')) bring(w.dataset.app);
    });
    $('.mac-reset', body).addEventListener('click', () => {
      timers.splice(0).forEach(clearTimeout);
      QUEUE.forEach(q => delete q.done);
      QUEUE.sort((a, b) => ['acme login redirect fix', 'nimbus api docs', 'chai shopify banner'].indexOf(a.t) - ['acme login redirect fix', 'nimbus api docs', 'chai shopify banner'].indexOf(b.t));
      now = 0; waiting = null; minutes = 10 * 60 + 24; clock(); intent();
      [...open].forEach(k => quit(k));
      front = null;
      isl.switchTo('Acme Studio');
      later(() => bring('code', true), 500);
      $('.dock-hint', body).classList.remove('gone');
    });
    clock(); intent();
    bring('code');
    isl.set('pill');
    caption('you\'re on it', 'open an app from the Dock and watch the island');
    return () => { timers.forEach(clearTimeout); isl.destroy(); };
  }

  /* ---- the window itself: grows out of the card's picture, and goes back into it ---- */
  let open = null;
  function openWindow(card) {
    if (open) return;
    const kind = card.dataset.play, src = $('.pic', card);
    const pw = document.createElement('div');
    pw.className = 'pw';
    pw.innerHTML = `<div class="pw-back"></div><div class="pw-win" role="dialog" aria-modal="true" aria-label="${kind === 'states' ? 'the island, live' : 'the nudge, live'}">
      <div class="pw-bar"><span class="pw-dots"><i></i><i></i><i></i></span><b>${kind === 'states' ? 'the island, live' : 'keeping you on track, live'}</b><span class="pw-live"><i></i>live</span>
      <button type="button" class="pw-x" aria-label="close">✕</button></div><div class="pw-body"></div></div>`;
    document.body.append(pw);
    const winEl = $('.pw-win', pw), body = $('.pw-body', pw);
    const stop = (kind === 'states' ? statesDemo : nudgeDemo)(body);
    const lastFocus = document.activeElement;
    document.documentElement.classList.add('pw-lock');
    const a = src.getBoundingClientRect(), b = winEl.getBoundingClientRect();
    src.style.visibility = 'hidden';
    if (!REDUCED) {
      winEl.animate([{transform: `translate(${a.left - b.left}px, ${a.top - b.top}px) scale(${a.width / b.width}, ${a.height / b.height})`, borderRadius: '10px'},
        {transform: 'none', borderRadius: '24px'}], {duration: 640, easing: SOFT});
      body.animate([{opacity: 0}, {opacity: 1}], {duration: 380, delay: 160, easing: 'ease-out', fill: 'backwards'});
      $('.pw-back', pw).animate([{opacity: 0}, {opacity: 1}], {duration: 400, easing: 'ease-out'});
    }
    $('.pw-x', pw).focus({preventScroll: true});
    const close = () => {
      if (!open) return;
      open = null;
      stop();
      removeEventListener('keydown', key, true);
      const done = () => { pw.remove(); src.style.visibility = ''; document.documentElement.classList.remove('pw-lock'); lastFocus?.focus?.({preventScroll: true}); };
      if (REDUCED) return done();
      const c = src.getBoundingClientRect(), d = winEl.getBoundingClientRect();
      body.animate([{opacity: 1}, {opacity: 0}], {duration: 160, fill: 'forwards'});
      $('.pw-back', pw).animate([{opacity: 1}, {opacity: 0}], {duration: 420, fill: 'forwards'});
      winEl.animate([{transform: 'none', borderRadius: '24px'}, {transform: `translate(${c.left - d.left}px, ${c.top - d.top}px) scale(${c.width / d.width}, ${c.height / d.height})`, borderRadius: '10px'}],
        {duration: 460, easing: 'cubic-bezier(.3,0,.1,1)', fill: 'forwards'}).onfinish = done;
    };
    const key = e => {
      if (e.key === 'Escape') { e.stopImmediatePropagation(); close(); }
      if (e.key === 'Tab') {  // keep focus inside the window
        const f = $$('button, a[href]', winEl).filter(x => x.offsetParent);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
        else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
      }
    };
    addEventListener('keydown', key, true);
    $('.pw-x', pw).addEventListener('click', close);
    $('.pw-back', pw).addEventListener('click', close);
    open = {close};
  }
  $$('[data-play]').forEach(card => {
    card.setAttribute('role', 'button');
    card.setAttribute('tabindex', '0');
    card.setAttribute('aria-haspopup', 'dialog');
    card.addEventListener('click', e => { if (!e.target.closest('a')) openWindow(card); });
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openWindow(card); } });
  });
})();
