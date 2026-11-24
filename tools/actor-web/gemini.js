/* tools/actor-web/gemini.js -- actor-pack.py --external jobs drawn in Gemini (gemini.google.com),
   in a browser already signed in, driven through the page's own DOM (README.md).

   Each job: a new chat (so no edit stacks on the last one), the composer cleared, the picture it is
   redrawn from pasted in, its prompt typed and sent, and the answer's picture fetched from the
   address the page shows it at (the preview's ".../gg-dl/<id>=s1024-rw" becomes "=d-I", which
   answers with the address of the original, "=s0-d-I", in two text hops: no download, nothing in
   the Downloads folder; Gemini draws about 842x1264, and the app's own "full size" download is
   that enlarged 2x), handed to tools/actor-web/receiver.py through its popup, which writes
   out/<key>.jpg. Run actor-pack.py --external again to gate what came back.

   Every step of a job checks that the job is still the current one (S.gen): a job given up on at
   its time limit stops at its next step instead of pasting into the next job's chat (the first
   runs did, and every later job failed with chats that "did not open").

     await AW.setup()                opens the receiver popup (receiver.py on 127.0.0.1:8899)
     await AW.load([...done])        queues the folder's jobs.json, skipping those keys
     AW.add([{key, prompt, ref}])    or queue entries by hand (ref: "refs/<key>.png")
     AW.start()                      runs the queue in the page; returns at once
     AW.status()                     {running, current, left, done, failed, log}
*/
(function () {
  'use strict';
  // gap: the pause between jobs; uploads come faster than Gemini takes them otherwise
  const S = { queue: [], done: [], failed: [], log: [], running: false, current: null, recv: null, gap: 12000, gen: 0 };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const say = m => { S.log.push(new Date().toISOString().slice(11, 19) + ' ' + m); if (S.log.length > 80) S.log.shift(); };
  const step = async (g, ms) => { await wait(ms); if (g !== S.gen) throw new Error('given up'); };

  function ask(kind, extra, answer, ms = 20000) {
    return new Promise((res, rej) => {
      const h = e => { if (e.data && e.data.kind === answer && (!extra.name || e.data.name === extra.name)) { removeEventListener('message', h); res(e.data); } };
      addEventListener('message', h);
      S.recv.postMessage(Object.assign({ kind }, extra), '*');
      // a popup that stops answering (Edge put it to sleep after ~20 minutes) is closed, and the
      // next job opens a fresh one (setup)
      setTimeout(() => { removeEventListener('message', h); try { S.recv.close(); } catch (e) {} rej(new Error(kind + ': no answer')); }, ms);
    });
  }

  async function setup() {
    // the picture's address is read from the page's resource timings: their buffer holds 250 by
    // default and stops recording when full
    performance.setResourceTimingBufferSize(100000);
    if (!S.recv || S.recv.closed) {
      S.recv = window.open('http://127.0.0.1:8899/recv.html', 'sfrecv', 'width=360,height=240');
      await wait(1500);
    }
    return 'receiver open';
  }

  const composer = () => document.querySelector('rich-textarea [contenteditable=true]');
  const responses = () => [...document.querySelectorAll('model-response')];
  // the composer's box: its attachments ("close picture" / "close attachment") and its text
  const box = () => { let e = document.querySelector('rich-textarea'); for (let k = 0; k < 6 && e; k++) e = e.parentElement; return e || document; };

  async function clearComposer(g) {  // "New chat" on an empty chat keeps the last draft
    for (let k = 0; k < 12; k++) {
      const x = [...box().querySelectorAll('button[aria-label]')].find(b => /^close (picture|attachment)/i.test(b.getAttribute('aria-label')));
      if (!x) break;
      x.click(); await step(g, 300);
    }
    const ed = composer(); ed.focus();
    document.execCommand('selectAll', false); document.execCommand('delete', false);
    await step(g, 300);
    if (box().querySelector('img[src^="blob:"]') || (composer().innerText || '').trim()) throw new Error('the composer did not clear');
  }

  async function newChat(g) {
    for (let attempt = 0; attempt < 3; attempt++) {
      const b = [...document.querySelectorAll('a[aria-label], button[aria-label]')]
        .find(x => /^new chat$/i.test(x.getAttribute('aria-label')));
      if (!b) throw new Error('no New chat button');
      b.click();
      for (let i = 0; i < 25; i++) { await step(g, 400); if (composer() && !responses().length) return clearComposer(g); }
    }
    throw new Error('the new chat did not open');
  }

  async function paste(g, url) {
    const blob = await (await fetch(url)).blob();
    const file = new File([blob], 'picture.png', { type: 'image/png' });
    const ed = composer(); ed.focus();
    const dt = new DataTransfer(); dt.items.add(file);
    ed.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    // a thumbnail once uploaded; a red mark and no thumbnail when Gemini refuses it (it does after
    // ~10 uploads in 3 minutes)
    for (let i = 0; i < 40; i++) {
      await step(g, 500);
      if (box().querySelector('img[src^="blob:"]')) { await step(g, 2500); if (box().querySelector('img[src^="blob:"]')) return; }
    }
    throw new Error('upload refused');
  }

  async function send(g, text) {
    const ed = composer(); ed.focus();
    document.execCommand('insertText', false, text);
    await step(g, 600);
    const b = [...document.querySelectorAll('button[aria-label]')].find(x => /^send/i.test(x.getAttribute('aria-label')));
    // a refused attachment leaves Send aria-disabled (not disabled), and a click does nothing
    if (!b || b.disabled || b.getAttribute('aria-disabled') === 'true') throw new Error('upload refused (send is off)');
    const asked = document.querySelectorAll('user-query').length;
    b.click();
    for (let i = 0; i < 30; i++) { await step(g, 500); if (document.querySelectorAll('user-query').length > asked) return; }
    throw new Error('the message did not go');
  }

  async function answer(g, before, seen) {
    for (let i = 0; i < 90; i++) {  // up to 3 minutes
      await step(g, 2000);
      const r = responses();
      if (r.length <= before) continue;
      const last = r[r.length - 1];
      const im = [...last.querySelectorAll('generated-image img, img.image')].find(x => x.naturalWidth > 300);
      if (im) {
        // the preview's address: .../gg-dl/<id>=s1024-rw?<query>; the full size is "=d-I"
        const urls = performance.getEntriesByType('resource').map(e => e.name).filter(u => !seen.has(u))
          .map(u => new URL(u)).filter(u => /^\/gg-dl\//.test(u.pathname) && /=s\d+-rw$/.test(u.pathname));
        if (urls.length) { const u = urls[urls.length - 1]; u.pathname = u.pathname.replace(/=s\d+-rw$/, '=d-I'); return u.href; }
      }
      const said = (last.innerText || '').trim();
      if (i > 20 && said && !last.querySelector('generated-image')) throw new Error('answered in words: ' + said.slice(0, 120));
    }
    throw new Error('no picture after 3 minutes');
  }

  async function follow(url) {  // the "=d-I" address answers with the next address, as text
    for (let hop = 0; hop < 6; hop++) {
      const r = await fetch(url, { credentials: 'include' });
      const b = await r.blob();
      if (/^image\//.test(b.type)) return b;
      const t = (await b.text()).trim();
      if (!/^https:\/\/\S+$/.test(t)) throw new Error('the picture address led to no picture');
      url = t;
    }
    throw new Error('the picture address went round');
  }

  async function one(g, job) {
    await newChat(g);
    const ref = await ask('aw-ref', { name: job.ref.replace(/^refs\//, '') }, 'aw-ref');
    if (ref.status !== 200) throw new Error('the receiver has no ' + job.ref);
    await paste(g, ref.url);
    performance.clearResourceTimings();
    const seen = new Set(performance.getEntriesByType('resource').map(e => e.name));
    const before = responses().length;
    await send(g, 'Edit this image. ' + job.prompt);
    const full = await answer(g, before, seen);
    const blob = await follow(full);
    if (g !== S.gen) throw new Error('given up');
    if (!/^image\//.test(blob.type) || blob.size < 20000) throw new Error('not a picture: ' + blob.type + ' ' + blob.size);
    const saved = await ask('aw-save', { name: job.key, blob }, 'aw-saved', 60000);
    if (saved.status !== 200) throw new Error('the receiver answered ' + saved.status);
    return blob.size;
  }

  async function loop() {
    S.running = true;
    while (S.queue.length && S.running) {
      const job = S.queue.shift(); S.current = job.key;
      await setup();
      const g = ++S.gen;
      let pause = S.gap;
      try {
        const n = await Promise.race([one(g, job), wait(300000).then(() => { throw new Error('no end after 300 s'); })]);
        S.done.push(job.key); say('done ' + job.key + ' ' + n + ' bytes');
      } catch (e) {
        S.gen++;  // whatever is left of this job stops at its next step
        job.tries = (job.tries || 0) + 1;
        say('failed ' + job.key + ': ' + e.message);
        if (job.tries < 3) S.queue.push(job); else S.failed.push({ key: job.key, why: e.message });
        if (/upload refused/.test(e.message)) pause = 120000;  // let Gemini's upload limit pass
      }
      await wait(pause);
    }
    S.running = false; S.current = null;
  }

  window.AW = {
    setup,
    async load(skip = []) { const m = await ask('aw-jobs', {}, 'aw-jobs'); return this.add(m.jobs.filter(j => j.ref && !skip.includes(j.key))); },
    add(jobs) { for (const j of jobs) if (!S.queue.some(q => q.key === j.key) && !S.done.includes(j.key)) S.queue.push(Object.assign({}, j)); return S.queue.length; },
    start() { if (!S.running) loop(); return 'started: ' + S.queue.length; },
    stop() { S.running = false; S.gen++; return 'stopped ' + S.current; },
    status() { return { running: S.running, current: S.current, left: S.queue.length, done: S.done.length, failed: S.failed, log: S.log.slice(-8) }; },
  };
})();
