// lowkey's real dashboard with no server: lowkey's own Python runs in this tab (Pyodide) on the demo week,
// and every /api/ request the page makes is answered by it. Nothing leaves the tab.
(() => {
  const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
  const net = window.fetch.bind(window);

  const veil = document.createElement('div');
  veil.id = 'webdemo-veil';
  veil.innerHTML = '<div><b>starting lowkey in your browser</b><span>loading Python and the demo week, one moment</span><i></i></div>';
  const css = document.createElement('style');
  css.textContent = `#webdemo-veil{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:#F3EEE3;
    font-family:"Bricolage Grotesque",system-ui,sans-serif;color:#111;transition:opacity .4s}
  #webdemo-veil div{display:grid;gap:10px;justify-items:center;text-align:center;padding:28px 34px;background:#FFFDF7;
    border:3px solid #111;border-radius:22px;box-shadow:6px 6px 0 #111;max-width:88vw}
  #webdemo-veil b{font-size:22px}#webdemo-veil span{color:#5d5a53}
  #webdemo-veil i{width:180px;height:10px;border:2.5px solid #111;border-radius:9px;overflow:hidden;position:relative}
  #webdemo-veil i:after{content:"";position:absolute;inset:0;width:40%;background:#B8FF3B;animation:wd 1.1s ease-in-out infinite alternate}
  @keyframes wd{to{transform:translateX(150%)}}
  #webdemo-bar{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);z-index:9998;max-width:calc(100vw - 24px);
    display:flex;gap:10px;align-items:center;padding:8px 10px 8px 16px;background:#111;color:#fff;border-radius:999px;
    font:600 13px "Bricolage Grotesque",system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25)}
  #webdemo-bar a{color:#111;background:#B8FF3B;padding:5px 12px;border-radius:999px;text-decoration:none;white-space:nowrap}
  @media (max-width:560px){#webdemo-bar span{display:none}}`;
  document.head.append(css);
  addEventListener('DOMContentLoaded', () => document.body.append(veil));

  const ready = (async () => {
    const py = await loadPyodide({indexURL: PYODIDE});
    py.unpackArchive(await (await net('lowkey.zip')).arrayBuffer(), 'zip', {extractDir: '/app'});
    py.runPython("import os, sys; sys.path.insert(0, '/app'); os.chdir('/app'); import webdemo");
    return py.globals.get('webdemo').handle;
  })();
  ready.catch(e => { veil.querySelector('span').textContent = `couldn't start: ${e.message}. try reloading.`; });

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
    veil.style.opacity = '0';
    setTimeout(() => veil.remove(), 450);
  }
})();
