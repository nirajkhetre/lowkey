// lowkey's real dashboard with no server: lowkey's own Python runs in this tab (Pyodide) on the demo week,
// and every /api/ request the page makes is answered by it. Nothing leaves the tab.
(() => {
  const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
  const net = window.fetch.bind(window);

  // The loading screen is lime: if you came through the landing page's "try it live" portal, it simply continues
  // that same lime screen; then it irises open onto the dashboard.
  let viaPortal = false;
  try { viaPortal = sessionStorage.getItem('lk-portal') === '1'; sessionStorage.removeItem('lk-portal'); } catch {}
  const veil = document.createElement('div');
  veil.id = 'webdemo-veil';
  veil.innerHTML = '<div class="wv-in"><span class="wv-mb"><i></i><i></i></span><b>starting lowkey in your browser</b>' +
    '<span class="wv-s">loading Python and the demo week, one moment</span><i class="wv-bar"></i></div>';
  const css = document.createElement('style');
  css.textContent = `#webdemo-veil{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:#B8FF3B;
    font-family:"Bricolage Grotesque",system-ui,sans-serif;color:#111}
  #webdemo-veil .wv-in{display:grid;gap:10px;justify-items:center;text-align:center;padding:24px;max-width:88vw}
  #webdemo-veil b{font-size:clamp(26px,4vw,40px);font-weight:800;letter-spacing:-.04em;line-height:1.05}
  #webdemo-veil .wv-s{font-size:16px;color:#2b3a10}
  .wv-mb{position:relative;display:block;width:88px;height:80px;margin-bottom:8px;border-radius:47% 47% 43% 43%/52% 52% 46% 46%;
    background:radial-gradient(circle at 34% 28%,#e6eeff 0,#7AA2FF 42%,#4467cf 100%);box-shadow:inset -4px -6px 10px rgba(0,0,0,.16);
    animation:wv-hop 1.1s cubic-bezier(.3,0,.2,1) infinite}
  .wv-mb i{position:absolute;top:33%;width:19%;height:25%;border-radius:50%;background:#111;animation:wv-blink 4s infinite}
  .wv-mb i:first-child{left:30%}.wv-mb i:last-child{right:30%}
  @keyframes wv-hop{0%,100%{transform:translateY(0) scale(1)}40%{transform:translateY(-14px) scale(.95,1.06)}70%{transform:translateY(0) scale(1.06,.94)}}
  @keyframes wv-blink{0%,92%,100%{transform:none}95%{transform:scaleY(.1)}}
  .wv-bar{position:relative;width:180px;height:10px;margin-top:8px;border:2.5px solid #111;border-radius:9px;overflow:hidden;background:#d8ff8f}
  .wv-bar:after{content:"";position:absolute;inset:0;width:40%;background:#111;border-radius:9px;animation:wd 1s ease-in-out infinite alternate}
  @keyframes wd{to{transform:translateX(150%)}}
  @media (prefers-reduced-motion:reduce){.wv-mb,.wv-mb i,.wv-bar:after{animation:none}}
  #webdemo-bar{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:9998;max-width:calc(100vw - 24px);
    display:flex;gap:10px;align-items:center;padding:8px 10px 8px 16px;background:#111;color:#fff;border-radius:999px;
    font:600 13px "Bricolage Grotesque",system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25)}
  #webdemo-bar a{color:#111;background:#B8FF3B;padding:5px 12px;border-radius:999px;text-decoration:none;white-space:nowrap}
  @media (max-width:560px){#webdemo-bar span{display:none}}`;
  document.head.append(css);
  document.documentElement.append(veil);  // right away, before the body paints: no flash of the dashboard
  if (!viaPortal && !matchMedia('(prefers-reduced-motion: reduce)').matches) veil.animate([{opacity: 0}, {opacity: 1}], {duration: 250});

  const ready = (async () => {
    const py = await loadPyodide({indexURL: PYODIDE});
    py.unpackArchive(await (await net('lowkey.zip')).arrayBuffer(), 'zip', {extractDir: '/app'});
    py.runPython("import os, sys; sys.path.insert(0, '/app'); os.chdir('/app'); import webdemo");
    return py.globals.get('webdemo').handle;
  })();
  ready.catch(e => { veil.querySelector('.wv-s').textContent = `couldn't start: ${e.message}. try reloading.`; });

  window.fetch = async (url, opts = {}) => {
    const u = new URL(url, location.href);
    const at = u.pathname.indexOf('/api/');
    if (at < 0) return net(url, opts);
    const handle = await ready;
    const {code, body} = JSON.parse(handle(opts.method || 'GET', u.pathname.slice(at) + u.search, opts.body || ''));
    if (u.pathname.endsWith('/api/state')) {
      body.model_ok = true;  // so the page shows Gemma's cached sentences; explain() says they're a replay
      setTimeout(explain, 60);  // after the page wrote its own (local-app) wording
    }
    if (u.pathname.endsWith('/api/brief') && body.brief) setTimeout(() => {
      const by = document.getElementById('briefBy');
      if (by) by.textContent = `gemma 4 wrote this from ${body.brief.lines} receipts on the author's laptop, when the demo week was made`;
    }, 60);
    return new Response(JSON.stringify(body), {status: code, headers: {'Content-Type': 'application/json'}});
  };

  function explain() {
    try { MIND.idle = 'web demo · gemma 4’s labels, replayed'; } catch {}
    const mind = document.getElementById('mindTxt');
    if (mind) mind.textContent = 'web demo · gemma 4’s labels, replayed';
    const foot = document.getElementById('foot');
    if (foot) foot.innerHTML = 'this is lowkey’s real dashboard and Python, running in your browser on a made-up <b>demo week</b>. ' +
      'the real app runs on your laptop with Gemma 4 via Ollama.<br>nothing you click here leaves this tab.';
    if (!document.getElementById('webdemo-bar')) {
      const bar = document.createElement('div');
      bar.id = 'webdemo-bar';
      bar.innerHTML = '<span>live demo · made-up week · runs in your browser</span><a href="../">about lowkey</a>' +
        '<a href="https://github.com/nirajkhetre/lowkey">get it</a>';
      document.body.append(bar);
    }
    if (!veil.isConnected || veil.dataset.out) return;
    veil.dataset.out = '1';
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return veil.remove();
    const pill = document.getElementById('modelPill')?.getBoundingClientRect();  // iris closes toward the model pill
    const at = pill ? `${pill.left + pill.width / 2}px ${pill.top + pill.height / 2}px` : '50% 50%';
    veil.querySelector('.wv-in').animate([{opacity: 1, transform: 'none'}, {opacity: 0, transform: 'scale(.9)'}], {duration: 220, fill: 'forwards'});
    veil.animate([{clipPath: `circle(150% at ${at})`}, {clipPath: `circle(0px at ${at})`}], {duration: 720, delay: 120, easing: 'cubic-bezier(.7,0,.25,1)', fill: 'forwards'})
      .onfinish = () => veil.remove();
  }
})();
