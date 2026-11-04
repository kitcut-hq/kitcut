// In-page queue runner for Grok Imagine (grok.com/imagine): makes one picture per job by driving
// the page's own DOM (composer, aspect menu, file input, Enter), and saves each through the local
// receiver (receiver.py beside this file) -- no screenshots, no clicks by coordinate, no per-picture
// tool calls. Install once per page load:
//   localStorage.setItem('sf_lib', <this file's text>); eval(localStorage.getItem('sf_lib'));
// then
//   SF.config({prefix, castPrompt, aspect: '16:9', width: 1792})   // stored in localStorage
//   SF.setRef('style', dataURL); SF.setRef('cast', dataURL)         // reference pictures
//   SF.add([{name: 's001', scene: '...', cast: true}, ...]); SF.start()
//   SF.status()                                                    // poll; never blocks
// The tab must stay the active tab of its window: a backgrounded Grok tab stops rendering.
(() => {
  const LS = (k, v) => (v === undefined ? localStorage.getItem('sf_' + k) : localStorage.setItem('sf_' + k, v));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const cfg = () => Object.assign({aspect: '16:9', width: 1792, timeout_s: 150, recv: 'http://127.0.0.1:8899/recv.html'},
    JSON.parse(LS('cfg') || '{}'));
  const S = (window.SF = window.SF || {queue: [], done: [], failed: [], running: false, current: null, log: []});
  const note = (t) => { S.log.push(new Date().toISOString().slice(11, 19) + ' ' + t); if (S.log.length > 60) S.log.shift(); };

  S.config = (c) => { LS('cfg', JSON.stringify(Object.assign(JSON.parse(LS('cfg') || '{}'), c))); return cfg(); };
  S.setRef = (k, dataURL) => { LS('ref_' + k, dataURL); return dataURL.length; };
  // load a picture from receiver.py --refs <dir> and keep it as reference `key`
  S.loadRef = (key, file) => new Promise((res, rej) => {
    const w = receiver();
    const on = (e) => {
      if (!e.data || e.data.kind !== 'still-film-ref' || e.data.name !== file) return;
      removeEventListener('message', on);
      if (!e.data.url) return rej(new Error('receiver has no ref ' + file + ' (' + e.data.status + ')'));
      res(S.setRef(key, e.data.url));
    };
    addEventListener('message', on);
    setTimeout(() => w.postMessage({kind: 'still-film-ref', name: file}, '*'), 1500);
  });
  S.add = (jobs) => { for (const j of jobs) S.queue.push(Object.assign({tries: 0}, j)); return S.queue.length; };
  S.stop = () => { S.running = false; return 'stopping after the current picture'; };
  S.status = () => ({running: S.running, current: S.current, left: S.queue.length,
    done: S.done.map((d) => d.name + ':' + d.size), failed: S.failed.map((f) => f.name + ':' + f.why), log: S.log.slice(-8)});

  const pid = () => (location.pathname.split('/post/')[1] || '').split('?')[0];
  const editor = () => document.querySelector('[contenteditable="true"]');
  const aspectBtn = () => [...document.querySelectorAll('button')].find((b) => b.getAttribute('aria-label') === 'Aspect Ratio');

  async function home() {
    if (location.pathname !== '/imagine') {
      const a = [...document.querySelectorAll('a[href="/imagine"]')].pop();
      if (a) a.click(); else history.back();
    }
    for (let i = 0; i < 40 && !(location.pathname === '/imagine' && editor()); i++) await wait(250);
    if (!editor()) throw new Error('no composer');
    await wait(400);
  }

  async function setAspect(want) {
    const b = aspectBtn();
    if (!b || b.textContent.trim() === want) return;
    b.click(); await wait(600);
    const it = [...document.querySelectorAll('div,button,[role=menuitemradio]')]
      .filter((e) => e.children.length < 4 && e.textContent.trim().startsWith(want));
    if (it.length) it[it.length - 1].click();
    await wait(600);
    if (aspectBtn() && aspectBtn().textContent.trim() !== want) throw new Error('aspect stayed ' + aspectBtn().textContent.trim());
  }

  async function attach(keys) {
    const dt = new DataTransfer();
    for (const k of keys) {
      const u = LS('ref_' + k); if (!u) throw new Error('missing ref ' + k);
      const b = await (await fetch(u)).blob();
      dt.items.add(new File([b], k + '.jpg', {type: b.type || 'image/jpeg'}));
    }
    const inp = [...document.querySelectorAll('input[type=file]')].find((x) => x.multiple);
    if (!inp) throw new Error('no file input');
    inp.files = dt.files; inp.dispatchEvent(new Event('change', {bubbles: true}));
    await wait(4500); // the upload; submitting sooner drops the picture
  }

  let recvWin = null;
  function receiver() {
    if (!recvWin || recvWin.closed) recvWin = window.open(cfg().recv, 'sfrecv', 'width=360,height=240');
    return recvWin;
  }
  const acks = {};
  window.addEventListener('message', (e) => {
    if (e.data && e.data.kind === 'still-film-saved') acks[e.data.name] = e.data.status;
  });

  async function save(name, blob) {
    delete acks[name];
    const w = receiver(); await wait(recvWin && recvWin.__warm ? 300 : 1500);
    try { recvWin.__warm = true; } catch (e) { /* cross-origin: fine */ }
    w.postMessage({kind: 'still-film-save', name, blob}, '*');
    for (let i = 0; i < 30 && !(name in acks); i++) await wait(300);
    if (!(name in acks)) throw new Error('receiver did not answer (is receiver.py running?)');
    if (!/^200/.test(acks[name])) throw new Error('receiver: ' + acks[name]);
  }

  async function one(job) {
    const c = cfg();
    await home();
    await setAspect(c.aspect);
    await attach(job.refs || (job.cast ? ['style', 'cast'] : ['style']));
    const ed = editor(); ed.focus();
    document.execCommand('insertText', false, (c.prefix || '') + (job.cast ? (c.castPrompt || '') : '') + 'Scene: ' + job.scene);
    await wait(500);
    ed.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true}));
    let im;
    for (let i = 0; i < c.timeout_s; i++) {
      const p = pid();
      if (p && !p.startsWith('tmp_')) {
        im = [...document.querySelectorAll('img')].find((x) => x.src.includes('/generated/' + p + '/') && x.naturalWidth === c.width && x.complete);
        if (im) break;
      }
      if (/Something went wrong|content moderated|couldn.t generate/i.test(document.body.innerText.slice(-4000))) throw new Error('grok refused or failed');
      await wait(1000);
    }
    if (!im) throw new Error('no picture after ' + c.timeout_s + ' s at ' + location.pathname);
    const blob = await (await fetch(im.src, {credentials: 'include'})).blob();
    await save(job.name, blob);
    return {name: job.name, size: blob.size, post: pid()};
  }

  S.start = () => {
    if (S.running) return 'already running';
    S.running = true;
    (async () => {
      while (S.running && S.queue.length) {
        const job = S.queue.shift(); S.current = job.name;
        try { const r = await one(job); S.done.push(r); note('saved ' + r.name + ' ' + r.size); }
        catch (e) {
          job.tries++; note(job.name + ' failed: ' + e.message);
          if (job.tries < 2) S.queue.push(job); else S.failed.push({name: job.name, why: e.message});
          await wait(3000);
        }
      }
      S.running = false; S.current = null; note('queue empty or stopped');
    })();
    return 'started, ' + S.queue.length + ' in queue';
  };
})();
