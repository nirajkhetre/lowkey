// The hero, alive: the island ticks, earns and charts your last hour, Gemma rewrites its line, the receipts wait for
// you to bill them, the creature watches you (and naps when you leave), and "try it live" opens like a portal.
(() => {
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const FINE = matchMedia('(pointer: fine)').matches;
  const $ = (s, el = document) => el.querySelector(s);
  const lerp = (a, b, t) => a + (b - a) * t;
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const money = n => '₹' + Math.round(n).toLocaleString('en-IN');
  const stage = $('.stage'), isl = $('.stage .isl');
  if (!stage || !isl) return;
  const hb = $('.hb', isl), typed = $('#typed'), msg = $('.hmsg', isl);

  /* ---- the session timer ticks, and today's money grows at Acme's rate (₹1,200/h) ---- */
  const t0 = Date.now() - (1 * 3600 + 24 * 60 + 7) * 1000;
  let earned = 5220, shown = 5220;
  setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    $('.htm', isl).textContent = `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
    earned += 1200 / 3600;
    if (Math.floor(earned) > shown) { shown = Math.floor(earned); setMoney(shown, false); }
  }, 1000);
  function setMoney(v, big) {
    const el = $('.hmo', isl);
    el.textContent = money(v);
    if (!REDUCED) el.animate([{color: '#fff', textShadow: '0 0 0 transparent'}, {color: '#B8FF3B', textShadow: '0 0 14px rgba(184,255,59,.8)'}, {color: '#B8FF3B'}],
      {duration: big ? 900 : 600, easing: 'ease-out'});
  }

  /* ---- the last hour, as a live chart that scrolls with time ---- */
  const svg = $('svg.live', isl), N = 22, W = 460, H = 50, STEP = W / (N - 1);
  let seed = 7;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  let k = 0;
  const next = () => { k++; return .5 + Math.sin(k * .55) * .22 + Math.sin(k * 1.7) * .1 + (rnd() - .5) * .18; };
  const data = Array.from({length: N + 1}, next);
  const y = v => H - 6 - Math.max(0, Math.min(1, v)) * (H - 12);
  function path() {  // Catmull-Rom through the points, as cubic Béziers
    const p = data.map((v, i) => [i * STEP, y(v)]);
    let d = `M${p[0][0]} ${p[0][1]}`;
    for (let i = 0; i < p.length - 1; i++) {
      const a = p[i - 1] || p[i], b = p[i], c = p[i + 1], e = p[i + 2] || c;
      d += ` C${b[0] + (c[0] - a[0]) / 6} ${b[1] + (c[1] - a[1]) / 6} ${c[0] - (e[0] - b[0]) / 6} ${c[1] - (e[1] - b[1]) / 6} ${c[0]} ${c[1]}`;
    }
    $('.ln', svg).setAttribute('d', d);
    $('.fill', svg).setAttribute('d', d + ` L${(p.length - 1) * STEP} ${H} L0 ${H} Z`);
  }
  path();
  const PERIOD = 1400;
  let last = performance.now();
  function chart(now) {
    let f = (now - last) / PERIOD;
    if (f >= 1) { data.shift(); data.push(next()); path(); last = now; f = 0; }
    if (!REDUCED) $('g', svg).setAttribute('transform', `translate(${-f * STEP} 0)`);
    const yy = y(lerp(data[N - 1], data[N], f));
    $('.dot', svg).setAttribute('cx', W - 6); $('.dot', svg).setAttribute('cy', yy);
    requestAnimationFrame(chart);
  }
  requestAnimationFrame(chart);

  /* ---- Gemma rewrites the line from time to time, from the demo week ---- */
  const LINES = ['Fixed OAuth redirect bug on the login page, reviewed PR #42', 'Developed auth logic and edited login.tsx for acme-website',
    'Designed the Acme landing page v3 in Figma', 'Ran the dev server and fixed the redirect in auth.ts'];
  let li = 0, writing = false;
  async function write(text) {
    writing = true;
    isl.classList.add('thinking');
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    while (typed.textContent.length) { typed.textContent = typed.textContent.slice(0, -2); await sleep(12); }
    await sleep(380);
    for (const ch of text) { typed.textContent += ch; await sleep(24 + Math.random() * 22); }
    isl.classList.remove('thinking');
    writing = false;
  }
  if (REDUCED) typed.textContent = LINES[0];
  else { setTimeout(() => write(LINES[0]), 700); setInterval(() => { if (!writing && !document.hidden && !isl.classList.contains('says')) write(LINES[li = (li + 1) % LINES.length]); }, 11000); }

  /* ---- the island says what just happened, in its own line ---- */
  let sayT;
  function say(text, mood) {
    clearTimeout(sayT);
    msg.innerHTML = text;
    isl.classList.add('says');
    if (mood) setMood(mood, 2200);
    sayT = setTimeout(() => isl.classList.remove('says'), 2600);
  }

  /* ---- the creature: eyes follow you, it naps when you leave, wakes when you're back ---- */
  let moodT, idleT, asleep = false, px = innerWidth / 2, py = 0;
  function setMood(m, ms) {
    clearTimeout(moodT);
    const blink = $('.g-blink', hb);
    blink.classList.add('shut');
    setTimeout(() => { hb.dataset.mood = m; blink.classList.remove('shut'); }, 110);
    if (ms) moodT = setTimeout(() => setMood(asleep ? 'away' : 'working'), ms);
  }
  const wake = () => {
    clearTimeout(idleT);
    if (asleep) { asleep = false; setMood('switched', 700); say('oh hi · back on the clock'); }
    idleT = setTimeout(() => { asleep = true; setMood('away'); }, 12000);
  };
  wake();
  addEventListener('pointermove', e => { px = e.clientX; py = e.clientY; wake(); }, {passive: true});
  addEventListener('keydown', wake);
  addEventListener('scroll', wake, {passive: true});
  const eyes = $('.g-eyes', hb);
  (function look() {
    const r = hb.getBoundingClientRect(), dx = px - (r.left + r.width / 2), dy = py - (r.top + r.height / 2), d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260);
    eyes.style.transform = asleep ? '' : `translate(${dx / d * k * 5}px, ${dy / d * k * 3.5}px)`;
    requestAnimationFrame(look);
  })();

  /* ---- receipts waiting for review: bill it, or nah ---- */
  const STACK = [
    {c: 'Acme Studio', col: '#B8FF3B', line: 'Fixed the OAuth redirect and reviewed PR #42.', mt: '1h 37m · ₹1,940 · gemma4 · 87% backed', worth: 1940},
    {c: 'Chai & Co', col: '#FF7AD9', line: 'Modified the product card theme, previewed Masala Chai 250g.', mt: '1h 20m · ₹1,200 · gemma4 · 92% backed', worth: 1200},
    {c: 'Nimbus Labs', col: '#7AA2FF', line: 'Coded handlers.py, ran tests, documented Nimbus API v2.', mt: '1h 45m · ₹2,625 · gemma4 · 94% backed', worth: 2625}];
  const rs = $('.rstack');
  let queue = [], billed = 0, busy = false;
  function deal() {
    queue = STACK.map(x => ({...x}));
    billed = 0;
    rs.innerHTML = '';
    queue.forEach((x, i) => {
      const c = document.createElement('div');
      c.className = 'card rcpt';
      c.innerHTML = `<span class="chip" style="background:${x.col};font-size:13px">${x.c}</span><div class="ln">${x.line}</div><div class="mt">${x.mt}</div>
        <div class="row"><button type="button" class="mini go" data-act="bill">bill it</button><button type="button" class="mini" data-act="nah">nah</button><span class="stamp" aria-hidden="true">✓ billed</span></div>`;
      x.el = c;
      rs.prepend(c);
    });
    layout(true);
    $('.hrev', isl).textContent = queue.length;
  }
  function layout(first) {
    queue.forEach((x, i) => { x.el.dataset.d = Math.min(i, 2); x.el.inert = i > 0; });
    if (first && !REDUCED) queue.forEach((x, i) => x.el.animate([{opacity: 0, transform: 'translateY(40px) scale(.9)'}, {opacity: 1, transform: 'none'}],
      {duration: 600, delay: 900 + i * 120, easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards'}));
  }
  rs.addEventListener('click', e => {
    const b = e.target.closest('[data-act]');
    if (!b || busy || !queue.length) return;
    const x = queue[0], bill = b.dataset.act === 'bill';
    busy = true;
    x.el.classList.add(bill ? 'billed' : 'skipped');
    if (bill) {
      billed += x.worth;
      fly(b.getBoundingClientRect(), `+${money(x.worth)}`, x.col, () => { say(`<b style="color:${x.col}">billed</b> · ${x.c} · ${money(x.worth)}`, 'goal'); });
    } else say(`left off the invoice · ${x.c}`, 'sidequest');
    setTimeout(() => {
      x.el.classList.add(bill ? 'away-up' : 'away-down');
      setTimeout(() => {
        x.el.remove();
        queue.shift();
        $('.hrev', isl).textContent = queue.length;
        layout();
        busy = false;
        if (!queue.length) done();
      }, 420);
    }, bill ? 700 : 260);
  });
  function done() {
    const c = document.createElement('div');
    c.className = 'card rcpt fin';
    c.innerHTML = `<div class="ln">all caught up.</div><div class="mt">${billed ? `${money(billed)} billed · only what you approved` : 'nothing billed · nothing reaches an invoice without you'}</div>
      <div class="row"><button type="button" class="mini" data-again>review again</button></div>`;
    rs.append(c);
    if (!REDUCED) c.animate([{opacity: 0, transform: 'scale(.85) rotate(-6deg)'}, {opacity: 1, transform: 'none'}], {duration: 520, easing: 'cubic-bezier(.2,0,0,1)'});
    $('[data-again]', c).addEventListener('click', deal);
  }
  function fly(rect, text, color, landed) {  // the capsule flies home to the island, like changes do in the app
    if (REDUCED) return landed();
    const el = document.createElement('div');
    el.className = 'cap-fly';
    el.textContent = text;
    el.style.background = color;
    document.body.append(el);
    const from = {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2}, s = performance.now(), dur = 760;
    const step = now => {
      const r = $('.mo', isl).getBoundingClientRect(), to = {x: r.left + r.width / 2, y: r.top + r.height / 2};
      const t = Math.min(1, (now - s) / dur), e = ease(t), u = 1 - e, c = {x: (from.x + to.x) / 2 + 60, y: Math.min(from.y, to.y) - 90};
      el.style.transform = `translate(${u * u * from.x + 2 * u * e * c.x + e * e * to.x}px, ${u * u * from.y + 2 * u * e * c.y + e * e * to.y}px) translate(-50%,-50%) scale(${1 - e * .5})`;
      el.style.opacity = t > .85 ? String((1 - t) / .15) : '1';
      if (t < 1) return requestAnimationFrame(step);
      el.remove();
      isl.animate([{transform: 'scale(1)'}, {transform: 'scale(1.03, .97)'}, {transform: 'scale(1)'}], {duration: 420, easing: 'cubic-bezier(.2,0,0,1)', composite: 'add'});
      landed();
    };
    requestAnimationFrame(step);
  }
  deal();

  /* ---- a little depth: the scene tilts toward your cursor ---- */
  const tilt = $('.tilt', stage);
  if (FINE && !REDUCED) {
    let tx = 0, ty = 0, gx = 0, gy = 0, raf = 0;
    const run = () => {
      tx = lerp(tx, gx, .12); ty = lerp(ty, gy, .12);
      tilt.style.transform = `rotateX(${ty}deg) rotateY(${tx}deg)`;
      raf = Math.abs(tx - gx) + Math.abs(ty - gy) > .01 ? requestAnimationFrame(run) : 0;
    };
    stage.addEventListener('pointermove', e => {
      const r = stage.getBoundingClientRect();
      gx = ((e.clientX - r.left) / r.width - .5) * 7; gy = -((e.clientY - r.top) / r.height - .5) * 6;
      if (!raf) raf = requestAnimationFrame(run);
    });
    stage.addEventListener('pointerleave', () => { gx = gy = 0; if (!raf) raf = requestAnimationFrame(run); });
  }

  /* ---- the scribble under "written" draws in, and again when you point at it ---- */
  const scrib = $('.scrib');
  if (scrib) scrib.addEventListener('pointerenter', () => { scrib.classList.remove('draw'); void scrib.offsetWidth; scrib.classList.add('draw'); });
  if (scrib) setTimeout(() => scrib.classList.add('draw'), 500);

  /* ---- "try it live": a lime portal opens out of the button, and the demo picks up on the same lime ---- */
  let warmed = false;
  const warm = () => {  // start fetching the demo while you hover, so it boots faster
    if (warmed) return;
    warmed = true;
    ['demo/', 'demo/demo.js', 'demo/lowkey.zip', 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js'].forEach(h => {
      const l = document.createElement('link'); l.rel = 'prefetch'; l.href = h; document.head.append(l);
    });
  };
  document.addEventListener('pointerover', e => { if (e.target.closest?.('a[href="demo/"]')) warm(); });
  document.addEventListener('focusin', e => { if (e.target.closest?.('a[href="demo/"]')) warm(); });
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href="demo/"]');
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || REDUCED) return;
    e.preventDefault();
    portal(a);
  });
  function portal(a) {
    const r = a.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const R = Math.hypot(Math.max(cx, innerWidth - cx), Math.max(cy, innerHeight - cy));
    const p = document.createElement('div');
    p.className = 'portal';
    p.innerHTML = `<div class="pt-in"><span class="mb" data-mood="switched"><span class="g-eyes"><span class="g-blink"><i></i><i></i></span></span></span>
      <b>opening the real dashboard</b><span>lowkey's own Python, starting in your browser</span><i class="pt-bar"></i></div>`;
    document.body.append(p);
    a.animate([{transform: 'scale(1)'}, {transform: 'scale(.9)'}, {transform: 'scale(1.06)'}], {duration: 260, easing: 'ease-out'});
    p.animate([{clipPath: `circle(${Math.max(r.width, r.height) / 2}px at ${cx}px ${cy}px)`, borderRadius: '0'}, {clipPath: `circle(${R}px at ${cx}px ${cy}px)`}],
      {duration: 680, easing: 'cubic-bezier(.75,0,.2,1)', fill: 'forwards'});
    $('.pt-in', p).animate([{opacity: 0, transform: 'translateY(14px) scale(.96)'}, {opacity: 1, transform: 'none'}], {duration: 420, delay: 260, easing: 'cubic-bezier(.2,0,0,1)', fill: 'backwards'});
    try { sessionStorage.setItem('lk-portal', '1'); } catch {}
    setTimeout(() => { location.href = a.href; }, 780);
  }
  addEventListener('pageshow', e => { if (e.persisted) document.querySelectorAll('.portal').forEach(p => p.remove()); });  // back from the demo: no leftover lime
})();
