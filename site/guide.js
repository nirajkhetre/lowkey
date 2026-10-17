// The guide: a Dynamic Island with lowkey's creature inside. It follows your cursor with its eyes, and when you
// pick a section (click it, or choose it from the island) it pops out, flies there, perches on the headline and
// explains it. One rAF loop drives the creature; CSS springs drive the island.
(() => {
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const FINE = matchMedia('(pointer: fine)').matches;
  const $ = s => document.querySelector(s);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;

  // what the guide says about each section: *word* is marked, `code` is code
  const SAY = {
    top: {name: 'the idea', lines: [
      'lowkey is a timesheet that *writes itself*. A notch at the top of your screen, like this one, always shows who you\'re working for.',
      'Every 5 minutes, *Gemma 4 on your own laptop* reads your window titles and writes an invoice-ready line. You approve it, it bills.',
      'The cards on the right are real lowkey UI: the island, one session\'s line, and the button that bills it.']},
    video: {name: 'the film', lines: [
      '99 seconds, start to finish: the problem, the island, the model writing your day, review, and the bill.',
      'Every screen in it is *real lowkey UI* rebuilt as motion. The clients and the money are demo data.',
      'Turn the sound on: there\'s a voiceover.']},
    how: {name: 'how it works', lines: [
      '*Step 1.* A tiny tracker notes the app and window title in front of you every 5 seconds. No screenshots, no keystrokes, and nothing while you\'re idle or have gone dark.',
      '*Step 2.* Every 5 minutes Gemma 4 E2B, through Ollama on your GPU, labels that slot. Its answer has to fit a schema whose client field is *your own list*, so it can\'t make a client up. About 0.46 s per label on an RTX 4050 laptop GPU.',
      '*Step 3.* Slots for the same client merge into sessions. Plain code scores how well the window titles back each one, and *nothing reaches an invoice until you approve it*.']},
    demo: {name: 'the live demo', lines: [
      'This isn\'t a recording. The button opens lowkey\'s *actual dashboard*, and its *actual Python* runs inside your browser tab.',
      'It\'s loaded with a made-up freelancer\'s week: bill or skip sessions, edit a line, ask *why?*, log a missed call, send the bill.',
      'Gemma can\'t run in a browser, so the demo *replays the labels it wrote* when the week was made. Nothing you click leaves the tab.']},
    details: {name: 'the details', lines: [
      'In the app, the island lives at the edge of your screen and opens when you hover, much like I just did.',
      'Drift to YouTube for 8 minutes and you get *one quiet nudge*. At most three an hour, and never over a fullscreen movie.',
      'Every client gets a creature like me, in their colour. We blink, follow your cursor, and *fall asleep when you walk away*.']},
    privacy: {name: 'privacy', lines: [
      'The dashboard only answers its own machine: it binds to `127.0.0.1` and turns away other hosts and other sites.',
      'Its only network call is to Ollama, *on your own computer*. No account, no telemetry, no cloud.',
      'Your activity is a plain JSONL file you can read, edit or delete. The code is MIT, so *you can check all of this*.']},
    install: {name: 'install', lines: [
      'You need Python 3.10+ and Ollama. The model is about 4.6 GB and fits a 6 GB laptop GPU. CPU works too, just slower.',
      'Start with `python -m lowkey --demo`: it tracks nothing and opens the demo week.',
      'Daily use is on Windows 11. The macOS and Linux trackers are tested, but *haven\'t run on real hardware yet*.']},
  };
  const IDS = Object.keys(SAY);
  const sec = id => document.getElementById(id);
  const anchorOf = id => sec(id)?.querySelector('h1, h2');

  /* ---------- DOM ---------- */
  document.body.insertAdjacentHTML('beforeend', `
    <div id="gisl" class="rest" role="button" tabindex="0" aria-haspopup="true" aria-expanded="false" aria-label="lowkey guide: pick a section to have it explained">
      <div class="g-glow"></div>
      <div class="g-face g-rest"><span class="g-slot"></span><span class="g-roll"><span class="g-now">ask me about this page</span></span><span class="g-spark">✦</span></div>
      <div class="g-face g-hello"><span class="g-slot"></span><span>hi! ${FINE ? 'double-click' : 'double-tap'} anything, or select some text, and I'll explain it.</span></div>
      <div class="g-face g-menu"><span class="g-slot"></span><b>where should I take you?</b>
        <div class="g-chips">${IDS.map((id, i) => `<button type="button" data-go="${id}"><i>${i + 1}</i>${SAY[id].name}</button>`).join('')}</div></div>
      <div class="g-face g-talk"><span class="g-dot"></span><span class="g-roll"><span class="g-what"></span></span><button type="button" class="g-home" aria-label="send the guide home">✕</button></div>
      <div class="g-prog"></div>
    </div>
    <div id="gbuddy" aria-hidden="true"><div class="g-shadow"></div><div class="g-body"><div class="g-eyes"><div class="g-blink"><i></i><i></i></div></div></div></div>
    <div id="gbubble" role="dialog" aria-live="polite" aria-label="lowkey guide" hidden>
      <div class="g-kick"><span class="g-sec"></span><span class="g-count"></span></div>
      <p class="g-text"></p>
      <div class="g-foot"><span class="g-dots"></span><button type="button" class="g-prev" aria-label="previous">‹</button><button type="button" class="g-next">next</button></div>
    </div>
    <div id="gtag" aria-hidden="true"><span>✦</span> double-click to ask</div>`);
  const isl = $('#gisl'), buddy = $('#gbuddy'), body = buddy.querySelector('.g-body'), eyes = buddy.querySelector('.g-eyes');
  const [eyeL, eyeR] = eyes.querySelectorAll('i'), shadow = buddy.querySelector('.g-shadow'), bub = $('#gbubble'), tag = $('#gtag');

  /* ---------- state ---------- */
  const B = {x: 0, y: 0, s: .42, mode: 'home', fx: 0, fy: 0, rot: 0, sx: 1, sy: 1};  // position: viewport when home, page otherwise
  let state = 'rest', at = null, step = 0, flight = null, mouse = {x: innerWidth / 2, y: 0, t: 0}, look = {x: 0, y: 0};
  let current = 'top';

  const slot = () => isl.querySelector(`.g-${state === 'menu' ? 'menu' : state === 'hello' ? 'hello' : 'rest'} .g-slot`);
  const home = () => { const r = slot().getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; };
  const setIsland = s => {
    state = s;
    isl.className = s;
    isl.setAttribute('aria-expanded', String(s === 'menu'));
  };

  /* ---------- the island ---------- */
  const roll = (el, text) => {  // the label rolls up to the new text, like a Live Activity
    if (el.textContent === text) return;
    if (REDUCED) { el.textContent = text; return; }
    el.animate([{transform: 'translateY(0)', opacity: 1, filter: 'blur(0)'}, {transform: 'translateY(-70%)', opacity: 0, filter: 'blur(3px)'}],
      {duration: 160, easing: 'cubic-bezier(.3,0,1,1)'}).onfinish = () => {
      el.textContent = text;
      el.animate([{transform: 'translateY(70%)', opacity: 0, filter: 'blur(3px)'}, {transform: 'translateY(0)', opacity: 1, filter: 'blur(0)'}],
        {duration: 320, easing: 'cubic-bezier(.2,0,0,1)'});
    };
  };
  const seen = new IntersectionObserver(es => {
    const vis = es.filter(e => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!vis) return;
    current = vis.target.id;
    if (state === 'rest' && !at) roll(isl.querySelector('.g-now'), `you're at · ${SAY[current].name}`);
  }, {threshold: [.25, .5, .75], rootMargin: '-20% 0px -30% 0px'});
  IDS.forEach(id => sec(id) && seen.observe(sec(id)));
  const progress = () => isl.style.setProperty('--p', (scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight)).toFixed(4));
  addEventListener('scroll', progress, {passive: true});
  progress();

  let closeT;
  const openMenu = () => { if (flight) return; clearTimeout(closeT); setIsland('menu'); };
  const closeMenu = (ms = 0) => { clearTimeout(closeT); closeT = setTimeout(() => state === 'menu' && setIsland(at ? 'talk' : 'rest'), ms); };
  if (FINE) {
    isl.addEventListener('pointerenter', () => !at && openMenu());
    isl.addEventListener('pointerleave', () => closeMenu(280));
  }
  isl.addEventListener('click', e => {
    const go = e.target.closest('[data-go]');
    if (go) return explain(go.dataset.go, 0, true);
    if (e.target.closest('.g-home')) return sendHome();
    if (state === 'menu') closeMenu(); else if (!at) openMenu();
  });
  isl.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target === isl) { e.preventDefault(); state === 'menu' ? closeMenu() : openMenu(); }
  });

  /* ---------- the creature ---------- */
  addEventListener('pointermove', e => { mouse = {x: e.clientX, y: e.clientY, t: performance.now()}; hover(e); }, {passive: true});

  function place() {
    const k = B.mode === 'home' ? 0 : 1;  // page coordinates once it's out, so it rides along with its section
    buddy.style.position = k ? 'absolute' : 'fixed';
    const bob = REDUCED || flight ? 0 : Math.sin(performance.now() / 560) * (B.mode === 'home' ? .8 : 2.2);
    buddy.style.transform = `translate(${B.x}px, ${B.y + bob}px) scale(${B.s})`;
    const breathe = REDUCED ? 0 : Math.sin(performance.now() / 900) * .025;
    body.style.transform = `rotate(${B.rot}deg) scale(${B.sx * (1 + breathe)}, ${B.sy * (1 - breathe)})`;
  }

  function eyesTick(now) {
    const r = body.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    let tx, ty;
    if (flight) { tx = flight.vx; ty = flight.vy; }  // look where it's going
    else if (now - mouse.t > 7000) { tx = Math.sin(now / 1300) * 120; ty = Math.cos(now / 1700) * 40; }  // idle: looks around
    else { tx = mouse.x - cx; ty = mouse.y - cy; }
    const d = Math.hypot(tx, ty) || 1, pull = Math.min(1, d / 260);
    look.x = lerp(look.x, tx / d * pull, .16);
    look.y = lerp(look.y, ty / d * pull, .16);
    eyes.style.transform = `translate(${look.x * 9}px, ${look.y * 6}px)`;
    const turn = look.x * .16;  // the far eye narrows: reads as the head turning
    eyeL.style.transform = `scaleX(${1 + Math.min(0, turn)})`;  // blinking is CSS (.g-blink), so it never sticks on a slow frame
    eyeR.style.transform = `scaleX(${1 - Math.max(0, turn)})`;
  }

  function frame(now) {
    if (B.mode === 'home') {
      const h = home();
      B.x = lerp(B.x, h.x - 32, .35); B.y = lerp(B.y, h.y - 32, .35);
    }
    if (flight) flight.tick(now);
    else if (at && !bub.hidden && now - (frame.lastFit || 0) > 250) { frame.lastFit = now; placeBubble(); }
    place();
    eyesTick(now);
    tagTick();
    requestAnimationFrame(frame);
  }

  /* ---------- flight ---------- */
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  function fly(aim, scaleTo, done) {  // aim: a point, or a function re-read every frame (the target can move)
    const goal = () => typeof aim === 'function' ? aim() : aim;
    let to = goal();
    const from = {x: B.x, y: B.y}, dist = Math.hypot(to.x - from.x, to.y - from.y);
    const dur = REDUCED ? 1 : clamp(420 + dist * .55, 620, 1250);
    const lift = Math.max(70, dist * .28), c = {x: (from.x + to.x) / 2, y: Math.min(from.y, to.y) - lift};
    const s0 = B.s, t0 = performance.now() + (REDUCED ? 0 : 130);
    if (!REDUCED) body.animate([{transform: body.style.transform}, {transform: 'scale(1.18, .78)'}], {duration: 130, easing: 'ease-out'});  // anticipation
    let prev = {...from};
    flight = {vx: to.x - from.x, vy: to.y - from.y, tick(now) {
      const t = clamp((now - t0) / dur, 0, 1), e = ease(t), u = 1 - e;
      if (now < t0) return;
      to = goal();
      B.x = u * u * from.x + 2 * u * e * c.x + e * e * to.x;
      B.y = u * u * from.y + 2 * u * e * c.y + e * e * to.y;
      B.s = lerp(s0, scaleTo, Math.min(1, t * 1.6));
      const vx = B.x - prev.x, vy = B.y - prev.y, sp = Math.hypot(vx, vy);
      prev = {x: B.x, y: B.y};
      flight.vx = vx * 40; flight.vy = vy * 40;
      const st = REDUCED ? 0 : clamp(sp / 26, 0, .32);  // stretch with speed, along the direction of travel
      B.rot = clamp(vx * 1.4, -24, 24);
      B.sx = 1 + st * .5; B.sy = 1 - st * .35;
      shadow.style.opacity = String(Math.max(0, e - .6) * 2.2);
      if (t >= 1) {
        flight = null; B.rot = 0; B.sx = B.sy = 1;
        if (!REDUCED) body.animate([{transform: 'scale(1.28, .7)'}, {transform: 'scale(.9, 1.12)'}, {transform: 'scale(1.04, .97)'}, {transform: 'scale(1, 1)'}],
          {duration: 520, easing: 'cubic-bezier(.2,0,0,1)'});  // squash on landing, then follow-through
        done && done();
      }
    }};
  }

  /* ---------- explaining ---------- */
  const esc = s => s.replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
  function write(text) {  // words write themselves in, the way the model's lines do in the app; *marked* and `code` runs stay whole
    const p = bub.querySelector('.g-text');
    p.innerHTML = text.split(/(\*[^*]+\*|`[^`]+`)/).filter(Boolean).map(run => {
      const kind = run[0] === '*' ? ' m' : run[0] === '`' ? ' c' : '', parts = (kind ? run.slice(1, -1) : run).split(/(\s+)/);
      // spaces stay between the words (inside a marked run they join it, so the highlight doesn't break)
      return parts.map((w, i) => /^\s*$/.test(w) ? (kind && i < parts.length - 1 ? '' : esc(w))
        : `<span class="w${kind}">${esc(w)}${kind && i < parts.length - 2 ? ' ' : ''}</span>`).join('');
    }).join('');
    p.querySelectorAll('.w').forEach((w, i) => w.style.transitionDelay = `${REDUCED ? 0 : 60 + i * 24}ms`);
    requestAnimationFrame(() => requestAnimationFrame(() => p.classList.add('in')));
    p.classList.remove('in');
  }
  function show(id) {
    const s = SAY[id];
    bub.querySelector('.g-sec').textContent = s.name;
    bub.querySelector('.g-count').textContent = `${step + 1} / ${s.lines.length}`;
    bub.querySelector('.g-dots').innerHTML = s.lines.map((_, i) => `<i class="${i === step ? 'on' : ''}"></i>`).join('');
    bub.querySelector('.g-prev').disabled = step === 0;
    bub.querySelector('.g-next').textContent = step === s.lines.length - 1 ? 'got it' : 'next';
    write(s.lines[step]);
  }
  function placeBubble() {
    const size = 64 * B.s, cx = B.x + 32 - scrollX, cy = B.y + 32 - scrollY;  // the creature's box, from its own state
    const r = {left: cx - size / 2, right: cx + size / 2, top: cy - size / 2, bottom: cy + size / 2, width: size};
    const w = Math.min(380, innerWidth - 32);
    bub.style.width = `${w}px`;
    const h = bub.offsetHeight;
    let x, y = r.top + scrollY - 6, side;
    if (r.right + 16 + w < innerWidth - 16) { x = r.right + 16; side = 'left'; }  // beside it if there's room,
    else {  // else below the headline, so you read the title, then the explanation
      const hb = at ? anchorOf(at).getBoundingClientRect().bottom : r.bottom;
      x = clamp(r.left + r.width / 2 - w * .7, 16, innerWidth - w - 16); y = Math.max(r.bottom, hb) + scrollY + 16; side = 'top';
    }
    bub.style.left = `${x}px`;
    bub.style.top = `${y}px`;
    bub.dataset.side = side;
    bub.style.setProperty('--tail', side === 'top' ? `${clamp(r.left + r.width / 2 - x, 24, w - 24)}px` : `${Math.min(28, h / 2)}px`);
  }
  function openBubble() {
    bub.hidden = false;
    placeBubble();
    if (!REDUCED) bub.animate([{opacity: 0, transform: 'scale(.6)', filter: 'blur(6px)'}, {opacity: 1, transform: 'scale(1.03)', filter: 'blur(0)', offset: .7}, {opacity: 1, transform: 'scale(1)'}],
      {duration: 460, easing: 'cubic-bezier(.2,0,0,1)'});
    bub.querySelector('.g-next').focus({preventScroll: true});
  }
  function closeBubble() {
    if (bub.hidden) return;
    const a = REDUCED ? null : bub.animate([{opacity: 1, transform: 'scale(1)'}, {opacity: 0, transform: 'scale(.7)', filter: 'blur(4px)'}], {duration: 200, easing: 'cubic-bezier(.3,0,1,1)'});
    const end = () => { bub.hidden = true; };
    a ? a.onfinish = end : end();
  }
  const focusRing = id => { document.querySelectorAll('.g-focus').forEach(e => e.classList.remove('g-focus')); id && sec(id)?.classList.add('g-focus'); };

  function perch(id) {  // stand at the end of the headline's last line, like a character after the sentence
    const h = anchorOf(id), range = document.createRange();
    range.selectNodeContents(h);
    const rects = [...range.getClientRects()].filter(r => r.width > 2), last = rects.reduce((a, r) => r.top > a.top + 4 ? r : a);
    const line = rects.filter(r => Math.abs(r.top - last.top) < 12).reduce((a, r) => ({left: Math.min(a.left, r.left), right: Math.max(a.right, r.right), top: Math.min(a.top, r.top), height: Math.max(a.height, r.height)}),
      {left: last.left, right: last.right, top: last.top, height: last.height});
    const roomRight = line.right + 14 + 64 < innerWidth - 12;
    const x = roomRight ? line.right + 14 : clamp(line.left + 24, 8, innerWidth - 76);
    let y = roomRight ? line.top + line.height / 2 - 34 : line.top - 62;  // beside the words, or on top if there's no room
    if (!roomRight && y < isl.getBoundingClientRect().bottom + 6) y = h.getBoundingClientRect().bottom + 4;  // no room above: stand under it
    return {x: x + scrollX, y: y + scrollY};
  }

  async function explain(id, s = 0, fromMenu = false) {
    if (!SAY[id] || flight) return;
    step = s;
    closeBubble();
    setIsland('talk');
    roll(isl.querySelector('.g-what'), `explaining · ${SAY[id].name}`);
    const h = anchorOf(id).getBoundingClientRect();
    if (fromMenu || h.top < 170 || h.top > innerHeight * .7) {  // bring the headline into view first, then fly
      const goal = clamp(scrollY + h.top - Math.max(innerHeight * .3, 220), 0, document.documentElement.scrollHeight - innerHeight);
      scrollTo({top: goal, behavior: REDUCED ? 'auto' : 'smooth'});
      await settle(goal);
    }
    const out = B.mode !== 'home', r = body.getBoundingClientRect();
    if (out && (r.bottom < 0 || r.top > innerHeight)) { toHome(); await new Promise(r => setTimeout(r, 40)); }
    if (B.mode === 'home') {  // out of the island: page coordinates from here on
      B.x += scrollX; B.y += scrollY; B.mode = 'out';
      isl.animate([{transform: 'translateX(-50%) scale(1)'}, {transform: 'translateX(-50%) scale(1.06, .92)'}, {transform: 'translateX(-50%) scale(1)'}], {duration: 380, easing: 'cubic-bezier(.2,0,0,1)'});
    }
    at = id;
    focusRing(id);
    fly(() => perch(id), 1, () => { show(id); openBubble(); });
  }
  function settle(goal) {  // resolve once the page has really arrived (or stopped trying)
    return new Promise(res => {
      let last = -1, still = 0;
      const t = setInterval(() => {
        still = scrollY === last ? still + 1 : 0;
        last = scrollY;
        if (Math.abs(scrollY - goal) < 2 || still > 8) { clearInterval(t); res(); }
      }, 50);
      setTimeout(() => { clearInterval(t); res(); }, 2500);
    });
  }
  function toHome() {  // instant, for when it's far off screen
    B.mode = 'home'; B.s = .42; const h = home(); B.x = h.x - 32; B.y = h.y - 32; shadow.style.opacity = '0';
  }
  function sendHome() {
    if (!at || flight) return;
    closeBubble();
    focusRing(null);
    const r = body.getBoundingClientRect();
    at = null;
    setIsland('rest');
    roll(isl.querySelector('.g-now'), `you're at · ${SAY[current].name}`);
    if (r.bottom < 0 || r.top > innerHeight) return toHome();
    shadow.style.opacity = '0';
    const h = home();
    fly({x: h.x - 32 + scrollX, y: h.y - 32 + scrollY}, .42, () => {
      toHome();
      if (!REDUCED) isl.animate([{transform: 'translateX(-50%) scale(1)'}, {transform: 'translateX(-50%) scale(1.08, .9)'}, {transform: 'translateX(-50%) scale(.98, 1.03)'}, {transform: 'translateX(-50%) scale(1)'}],
        {duration: 520, easing: 'cubic-bezier(.2,0,0,1)'});  // the gulp
      isl.focus({preventScroll: true});
    });
  }

  bub.querySelector('.g-next').addEventListener('click', () => {
    if (step < SAY[at].lines.length - 1) { step++; show(at); placeBubble(); } else sendHome();
  });
  bub.querySelector('.g-prev').addEventListener('click', () => { if (step > 0) { step--; show(at); placeBubble(); } });
  addEventListener('keydown', e => {
    if (e.key === 'Escape') { if (at) sendHome(); else closeMenu(); }
    if (at && !bub.hidden && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) bub.querySelector(e.key === 'ArrowRight' ? '.g-next' : '.g-prev').click();
  });
  addEventListener('resize', () => { if (at && !flight) { const p = perch(at); B.x = p.x; B.y = p.y; placeBubble(); } });

  /* ---------- summon: double-click / double-tap a section, or select some text in it ---------- */
  // A single click never summons the guide: clicks are for reading, links and buttons.
  const SKIP = 'a, button, iframe, input, textarea, pre, code, #gbubble, #gisl, nav, .video';
  const SECTIONS = IDS.map(i => '#' + i).join(',');
  const sectionOf = node => {
    const el = node?.nodeType === 1 ? node : node?.parentElement, s = el?.closest(SECTIONS);
    return s && !el.closest(SKIP) ? s : null;
  };
  const target = e => sectionOf(e.target);
  let lastAsk = {id: null, t: 0};
  function ask(s) {
    if (!s || (s.id === at && !bub.hidden)) return;
    const now = performance.now();
    if (s.id === lastAsk.id && now - lastAsk.t < 900) return;  // a double-click also selects a word: one summon, not two
    lastAsk = {id: s.id, t: now};
    explain(s.id);
  }
  document.addEventListener('dblclick', e => ask(target(e)));
  let tap = {t: 0, x: 0, y: 0}, down = false, selT;
  document.addEventListener('pointerdown', () => { down = true; });
  document.addEventListener('pointerup', e => {
    down = false;
    if (e.pointerType === 'touch') {  // double-tap, for phones that don't send dblclick
      const now = performance.now(), near = Math.hypot(e.clientX - tap.x, e.clientY - tap.y) < 30;
      if (now - tap.t < 320 && near) ask(target(e));
      tap = {t: now, x: e.clientX, y: e.clientY};
    }
    setTimeout(selected, 0);
  });
  document.addEventListener('selectionchange', () => { clearTimeout(selT); selT = setTimeout(() => !down && selected(), 500); });  // phones: once the handles settle
  function selected() {
    const sel = getSelection();
    if (sel.isCollapsed || sel.toString().trim().length < 3) return;
    const a = sectionOf(sel.anchorNode);
    if (a && a === sectionOf(sel.focusNode)) ask(a);
  }

  // the "ask lowkey" tag trails the pointer over parts it can explain
  let tagOn = false, tx = 0, ty = 0;
  function hover(e) {
    if (!FINE) return;
    const s = target(e);
    const on = !!s && !flight && !(s.id === at && !bub.hidden);
    if (on !== tagOn) { tagOn = on; tag.classList.toggle('on', on); if (on) { tx = e.clientX; ty = e.clientY; } }
  }
  function tagTick() {
    if (!tagOn) return;
    tx = lerp(tx, mouse.x + 18, .22); ty = lerp(ty, mouse.y + 20, .22);
    tag.style.transform = `translate(${tx}px, ${ty}px)`;
  }

  /* ---------- hello ---------- */
  toHome();
  requestAnimationFrame(frame);
  const link = location.hash.match(/^#ask=(\w+)/);  // shareable: lowkey.nirajlabs.tech/#ask=privacy
  if (link && SAY[link[1]]) return setTimeout(() => explain(link[1], 0, true), 700);
  setTimeout(() => {
    if (state !== 'rest' || at) return;
    setIsland('hello');
    if (!REDUCED) body.animate([{transform: 'translateY(0)'}, {transform: 'translateY(-7px) scale(.95, 1.06)'}, {transform: 'translateY(0) scale(1.06, .94)'}, {transform: 'none'}], {duration: 620, delay: 380, easing: 'cubic-bezier(.2,0,0,1)'});
    setTimeout(() => state === 'hello' && setIsland('rest'), 4200);
  }, 1100);
})();
