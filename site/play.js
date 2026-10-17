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

  // ---- window 2: the nudge story ----
  function nudgeDemo(body) {
    body.innerHTML = `<div class="dsk"><div class="dsk-wall"></div>
        <div class="dsk-win code" style="left:4%;top:20%;width:58%;height:66%"><div class="dsk-bar"><b></b><b></b><b></b><span>login.tsx — acme-website</span></div>${'<i></i>'.repeat(7)}</div>
        <div class="dsk-win yt" style="left:28%;top:24%;width:60%;height:66%"><div class="dsk-bar"><b></b><b></b><b></b><span>YouTube · lofi hip hop radio</span></div><div class="vid"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="56" fill="rgba(255,255,255,.18)"/><path d="M48 38 L86 60 L48 82 Z" fill="#fff"/></svg></div></div>
        <div class="dsk-win pm" style="left:22%;top:26%;width:66%;height:64%"><div class="dsk-bar"><b></b><b></b><b></b><span>POST /v2/invoices · nimbus-api · Postman</span></div><p><span class="verb">POST</span> /v2/invoices</p>${'<i></i>'.repeat(4)}</div>
        <div class="dsk-now"><span>now</span><b>acme login redirect fix</b><em>24 of 60 min</em></div>
        ${islandHTML()}
        <div class="dsk-cap"><b>you're on it</b><span>lowkey watches the window titles, not your screen</span></div></div>
      <div class="pw-ctl"><span class="pw-k">play it</span><button type="button" class="chip-s" data-s="drift">drift to YouTube</button><button type="button" class="chip-s" data-s="move">move on to Nimbus</button><button type="button" class="chip-s ghost" data-s="reset">start over</button>
        <span class="pw-tip">a simulation of the app's island · nothing here watches you</span></div>`;
    const isl = Island(body), dsk = $('.dsk', body), cap = $('.dsk-cap', body);
    let busy = [];
    const later = (f, ms) => busy.push(setTimeout(f, ms));
    const caption = (b, s) => { $('b', cap).textContent = b; $('span', cap).textContent = s; };
    const win = (cls, on) => $(`.dsk-win.${cls}`, body).classList.toggle('in', on);
    const reset = () => {
      busy.forEach(clearTimeout); busy = [];
      win('yt', false); win('pm', false);
      $('.dsk-now b', body).textContent = 'acme login redirect fix'; $('.dsk-now em', body).textContent = '24 of 60 min';
      dsk.classList.remove('done');
      if (isl.client !== 'Acme Studio') { isl.switchTo('Acme Studio'); }
      isl.set('pill');
      caption('you\'re on it', 'lowkey watches the window titles, not your screen');
    };
    const next = () => {
      caption('then, what\'s next', 'with the reason: due soon, better paid, waiting longest');
      isl.prompt('next up: nimbus api docs', '₹1,500/h · nice, that took 52m', [
        {label: 'later', on: () => { isl.toast('it keeps its place in line'); caption('later is fine', 'what\'s next waits for you'); }},
        {label: 'start it', kind: 'blue', on: () => {
          win('pm', true); isl.switchTo('Nimbus Labs'); dsk.classList.remove('done');
          $('.dsk-now b', body).textContent = 'nimbus api docs'; $('.dsk-now em', body).textContent = '0 of 120 min';
          caption('on it', 'the timer starts, in Nimbus blue');
          later(() => isl.set('pill'), 2700);
        }}], 'switched');
    };
    const ask = (sub) => {
      caption('moved on? one tap', 'how far you got, in your words, not a guess');
      isl.prompt('how far did you get?', sub, ['just started', 'halfway', 'almost', 'done'].map((l, i) => ({label: l, kind: i === 3 ? 'go' : '', on: () => {
        dsk.classList.toggle('done', i === 3);
        isl.toast(i === 3 ? 'done · nice, that took 52m' : `saved · ${l}`, {ms: 1700, then: next});
        if (i === 3) $('[data-f=toast] .mb', isl.el).dataset.mood = 'milestone'; else $('[data-f=toast] .mb', isl.el).dataset.mood = 'working';
      }})), 'switched');
    };
    $('.pw-ctl', body).addEventListener('click', e => {
      const s = e.target.closest('[data-s]')?.dataset.s;
      if (!s) return;
      if (s === 'reset') return reset();
      reset();
      if (s === 'drift') {
        later(() => { win('yt', true); caption('8 minutes later…', 'only real distractions count, never while you\'re away'); }, 250);
        later(() => {
          caption('drifted? a nudge', 'at most three an hour, never over a fullscreen movie');
          isl.prompt('8 min on YouTube', 'back to acme login redirect fix?', [
            {label: 'switch', on: () => { win('yt', false); ask('acme login redirect fix · it keeps its place in line'); }},
            {label: 'later', on: () => { isl.toast('ok · I won\'t nag'); caption('later counts too', 'an ignored nudge just means later'); }},
            {label: 'back on it', kind: 'go', on: () => { win('yt', false); $('[data-f=toast] .mb', isl.el).dataset.mood = 'goal'; isl.toast('back on acme login redirect fix'); caption('back on it', 'one tap, and the nudge is gone'); }},
          ], 'unsure');
        }, 1400);
      }
      if (s === 'move') {
        later(() => { win('pm', true); caption('you open Postman…', 'Nimbus Labs\' hints are in the window title'); }, 250);
        later(() => ask('acme login redirect fix · you\'ve moved on to Nimbus Labs'), 1500);
      }
    });
    isl.set('pill');
    return () => { busy.forEach(clearTimeout); isl.destroy(); };
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
