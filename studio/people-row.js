// The People row of a film composer: photos of people the studio draws into the film as characters
// who talk (lib/people.js has the rules; kitcut studio/film.py's "people" capability makes them).
// One piece for every composer -- the home page's (index.html) and a project's episode box
// (projects.html) -- so both look, read and behave alike. A classic script with no dependencies,
// because the studio machine serves it beside its copy of index.html; it declares nothing global
// but PeopleRow. Its look is app.css's (.people). test/people.test.mjs holds its lists to
// lib/people.js and the studio's /api/limits.
//
//   const P = PeopleRow.create({ shrink, upload, canUpload, onChange })
//     shrink(file) -> {blob, w, h}   the page's picture shrinker (2048 px, no location data)
//     upload(blob) -> {id}           sends one photo (default: POST /api/uploads). Throw
//                                    PeopleRow.later() for "not now" (signed out): kept, sent by sync()
//     canUpload() -> bool            whether photos may go up yet (default: always)
//     onChange(why, count)           why: add, remove, name, style, clear, restore
//     peek(url)                      a photo clicked: shown big (optional)
//   P.mount(el, {look, heard, what}) draws it into el; call again after a re-render, the people stay.
//                                    heard: false under an ElevenLabs narrator (seen, not heard)
//   P.setLook(look)                  Auto follows the film's look
//   P.add(files)                     a person from a photo (the Add a person button uses it)
//   P.sync()                         sends the photos not sent yet, once the page may
//   P.check()                        '' or why the film cannot start: the tick, a photo that failed
//   P.ready(say)                     resolves once every photo is up (say(text) while it waits)
//   P.body()                         {people, character_style, people_consent}, or {} for nobody
//   P.lost(id)                       a photo the studio no longer has (a day old): sent again
//   P.clear()                        the film took them
//   P.save() / P.restore(saved)      what a page keeps in its draft: the photos, names and style
//   P.count()
const PeopleRow = (() => {
  // lib/people.js PEOPLE_STYLES, STYLE_LABEL, STYLE_AUTO, MAX_PEOPLE, PERSON_NAME_MAX
  const STYLES = ['auto', 'crayon', 'papercut', 'newspaper', 'woodcut', 'watercolour', 'popart', 'courtroom', 'chalk', 'sticker', 'felt', 'knit', 'peg', 'sock'];
  const LABEL = {
    auto: 'Auto', crayon: 'Crayon', papercut: 'Paper cut-out', newspaper: 'Newspaper', woodcut: 'Woodcut',
    watercolour: 'Watercolour', popart: 'Pop art', courtroom: 'Courtroom sketch', chalk: 'Chalk',
    sticker: 'Sticker', felt: 'Felt puppet', knit: 'Knitted doll', peg: 'Wooden toy', sock: 'Sock puppet',
  };
  const AUTO = { drawn: 'crayon', painted: 'watercolour', collage: 'papercut' };
  const LOOK_NAME = { drawn: 'Hand-drawn', painted: 'Painted', collage: 'Collage' };
  const MAX = 4, NAME_MAX = 40;
  const still = matchMedia('(prefers-reduced-motion: reduce)');
  const playOf = (v) => () => { if (still.matches || !v || !v.isConnected) return; if (!v.src) v.src = v.dataset.src; v.play().catch(() => {}); };
  const later = (why = 'later') => Object.assign(new Error(why), { later: true });
  const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));
  async function postUpload(blob) {
    const r = await fetch('/api/uploads', { method: 'POST', headers: { 'Content-Type': blob.type }, body: blob });
    const b = await r.json().catch(() => ({}));
    if (r.status === 401) throw later('signin');
    if (!r.ok) throw new Error(b.error || `HTTP ${r.status}`);
    return b;
  }

  function create({ shrink, upload = postUpload, canUpload = () => true, onChange = () => {}, peek = null }) {
    const S = { list: [], style: 'auto', consent: false, look: 'drawn', heard: true, what: 'film', root: null };
    const q = (sel) => S.root && S.root.querySelector(sel);
    const auto = () => AUTO[S.look] || 'crayon';
    function about() {
      const quiet = S.heard ? '' : ` The ${S.what} is narrated in its ElevenLabs voice, so they are seen, not heard.`;
      if (!S.list.length) return `Add a photo of anyone who should be in the ${S.what}: they become a drawn character${S.heard ? ' who talks in their own voice' : ''}.${quiet}`;
      return S.heard ? `Each becomes a drawn character who talks in their own voice. Say in your idea what they talk about; a name lets the ${S.what} introduce them.`
        : `Each becomes a drawn character.${quiet} Say in your idea what they do.`;
    }
    const tile = (k) => {
      const pic = k === 'auto' ? auto() : k;
      return `<label class="st"><input type="radio" name="pstyle" value="${k}"${k === S.style ? ' checked' : ''}><span class="pv">`
        + `<img src="/people/${pic}.jpg" alt="" loading="lazy" onerror="this.remove()">`
        + `<video muted loop playsinline preload="none" data-src="/people/${pic}.mp4"></video>${k === 'auto' ? '<i>Auto</i>' : ''}</span><b>${LABEL[k]}</b></label>`;
    };

    function mount(root, { look = S.look, heard = true, what = 'film' } = {}) {
      S.root = root; S.look = look; S.heard = heard; S.what = what;
      root.innerHTML = `<section class="people" aria-label="People in the ${what}">
        <p class="phead"><b>People in the ${what}</b><span data-about></span></p>
        <div class="prow">
          <div class="prow" data-tiles></div>
          <button type="button" class="padd" data-add title="A photo of one person, face to the camera, like a passport photo or a profile picture">
            <span class="demo" aria-hidden="true"><img class="src" src="/people/photo.jpg" alt="" onerror="this.remove()"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h15M13 6l6 6-6 6"/></svg><span class="toon"><img src="/people/cycle.jpg" alt="" onerror="this.remove()"><video muted loop playsinline preload="none" data-src="/people/cycle.mp4"></video></span></span>
            <b>Add a person</b>
          </button>
          <input type="file" accept="image/*" hidden data-file>
        </div>
        <div class="pstyle" data-pstyle hidden>
          <p class="phead"><b>Drawn as</b><span data-style-about aria-live="polite"></span></p>
          <div class="styles" role="radiogroup" aria-label="Character style">${STYLES.map(tile).join('')}</div>
          <label class="consent" data-consent-row><input type="checkbox" data-consent${S.consent ? ' checked' : ''}> I have permission to use these people's photos.</label>
        </div>
        <p class="pnote" data-note aria-live="polite" hidden></p>
      </section>`;
      q('[data-add]').onclick = () => q('[data-file]').click();
      q('[data-file]').onchange = (e) => { add(e.target.files); e.target.value = ''; };
      q('[data-consent]').onchange = (e) => { S.consent = e.target.checked; q('[data-consent-row]').classList.remove('need'); };
      for (const st of root.querySelectorAll('.st')) {
        const v = st.querySelector('video'), input = st.querySelector('input'), play = playOf(v), stop = () => v.pause();
        st.addEventListener('mouseenter', play); st.addEventListener('mouseleave', stop);
        input.addEventListener('focus', play); input.addEventListener('blur', stop);
        input.addEventListener('change', () => { S.style = input.value; paint(); onChange('style', S.list.length); });
        v.addEventListener('error', () => v.remove());
      }
      // the add tile shows what it does, in every style in turn, while it is on screen
      const demo = q('.padd video'), go = playOf(demo);
      demo.addEventListener('error', () => demo.remove());
      if ('IntersectionObserver' in window) new IntersectionObserver((es) => es.forEach((e) => (e.isIntersecting ? go() : demo.pause()))).observe(q('[data-add]'));
      else go();
      paint();
    }
    function setLook(look) {
      S.look = look;
      const img = q('.st input[value=auto] + .pv img'), v = q('.st input[value=auto] + .pv video');
      if (img) img.src = `/people/${auto()}.jpg`;
      if (v) { v.pause(); v.removeAttribute('src'); v.dataset.src = `/people/${auto()}.mp4`; v.load(); }
      paint();
    }
    function paint() {
      if (!S.root) return;
      const on = S.list.length > 0;
      q('.people').classList.toggle('on', on);
      q('[data-pstyle]').hidden = !on;
      q('[data-add]').hidden = S.list.length >= MAX;
      q('[data-about]').textContent = about();
      q('[data-style-about]').textContent = S.style === 'auto'
        ? `${LABEL[auto()]}, to suit the ${LOOK_NAME[S.look] || 'Hand-drawn'} look. Pick another to draw everyone that way.`
        : `Everyone in the ${S.what} is drawn as a ${LABEL[S.style].toLowerCase()} character.`;
      const radio = q(`.st input[value="${S.style}"]`);
      if (radio && !radio.checked) radio.checked = true;
      if (!on) { S.consent = false; q('[data-consent]').checked = false; q('[data-consent-row]').classList.remove('need'); }
      // the name fields keep their focus and caret: tiles are only added and taken away, never redrawn
      const tiles = q('[data-tiles]');
      for (const el of [...tiles.children]) if (!S.list.includes(el._p)) el.remove();
      S.list.forEach((p, i) => {
        let f = [...tiles.children].find((el) => el._p === p);
        if (!f) {
          f = document.createElement('figure');
          f._p = p;
          f.innerHTML = '<span class="ph"><img alt=""></span><button type="button" class="x">&times;</button>'
            + `<input type="text" maxlength="${NAME_MAX}" autocomplete="off" spellcheck="false" placeholder="Name, e.g. Alex">`;
          f.querySelector('img').src = p.url;
          if (peek) { f.querySelector('img').style.cursor = 'zoom-in'; f.querySelector('img').onclick = () => peek(p.url); }
          f.querySelector('.x').onclick = () => remove(p);
          const name = f.querySelector('input');
          name.value = p.name;
          name.addEventListener('input', () => { p.name = name.value; });
          name.addEventListener('change', () => onChange('name', S.list.length));
          tiles.append(f);
        }
        f.className = `person${p.state === 'uploading' ? ' busy' : ''}${p.state === 'error' ? ' bad' : ''}`;
        f.title = p.error || '';
        f.querySelector('img').alt = `Person ${i + 1}`;
        f.querySelector('.x').setAttribute('aria-label', `Remove person ${i + 1}`);
        f.querySelector('input').setAttribute('aria-label', `Person ${i + 1}'s name`);
        if (tiles.children[i] !== f) tiles.insertBefore(f, tiles.children[i]);
      });
    }
    function note(t) { const n = q('[data-note]'); if (n) { n.textContent = t || ''; n.hidden = !t; } }
    function remove(p) { URL.revokeObjectURL(p.url); S.list = S.list.filter((x) => x !== p); paint(); onChange('remove', S.list.length); }
    async function send(p) {
      if (!canUpload()) { p.state = 'local'; return; }
      p.state = 'uploading'; p.error = ''; paint();
      try {
        p.id = (await upload(p.blob)).id; p.state = 'ready';
      } catch (e) {
        if (e.later) p.state = 'local';
        else { p.state = 'error'; p.error = String(e.message || e); }
      }
      paint();
    }
    const sync = () => Promise.all(S.list.filter((p) => !p.id && p.state === 'local').map(send));
    async function add(files) {
      const f = [...files].find((x) => x.type.startsWith('image/') || /\.(heic|heif)$/i.test(x.name));
      if (!f) return note('A person is a photo (JPG, PNG, WebP).');
      if (S.list.length >= MAX) return note(`Up to ${MAX} people a ${S.what}.`);
      note('');
      let p;
      try {
        const s = await shrink(f);
        p = { blob: s.blob, w: s.w, h: s.h, url: URL.createObjectURL(s.blob), name: '', id: null, state: 'local', error: '' };
      } catch (e) {
        return note(`“${f.name}” could not be opened here. Try a JPG or PNG (on an iPhone, a screenshot of the photo works).`);
      }
      S.list.push(p); paint(); onChange('add', S.list.length);
      const names = q('[data-tiles]')?.querySelectorAll('input');
      if (names && names.length) names[names.length - 1].focus();
      await send(p);
    }
    function check() {
      if (!S.list.length) return '';
      const bad = S.list.find((p) => p.state === 'error');
      if (bad) return `A person's photo could not be added (${bad.error}): remove it and add it again.`;
      if (!S.consent) {
        q('[data-consent-row]')?.classList.add('need'); q('[data-consent]')?.focus();
        return 'Tick the box to say you may use these people\'s photos.';
      }
      return '';
    }
    async function ready(say = () => {}) {
      for (let i = 0; i < 120; i++) {
        const bad = S.list.find((p) => p.state === 'error');
        if (bad) throw new Error(`A person's photo could not be added (${bad.error}): remove it and add it again.`);
        if (S.list.every((p) => p.id && p.state === 'ready')) return;
        say('Sending the people\'s photos...');
        if (S.list.some((p) => p.state === 'local')) await sync();
        await sleep(1000);
      }
      throw new Error('The people\'s photos are taking too long to send. Try again in a minute.');
    }
    const body = () => (S.list.length ? {
      people: S.list.map((p) => ({ upload: p.id, name: p.name.trim() })), character_style: S.style, people_consent: S.consent,
    } : {});
    function lost(id) {
      const p = S.list.find((x) => x.id === id);
      if (!p) return false;
      p.id = null; p.state = 'local'; send(p);
      return true;
    }
    function clear() { for (const p of S.list) URL.revokeObjectURL(p.url); S.list = []; S.consent = false; paint(); onChange('clear', 0); }
    const save = () => ({ style: S.style, people: S.list.map(({ blob, w, h, name, id }) => ({ blob, w, h, name, id })) });
    function restore(saved) {
      if (!saved || !Array.isArray(saved.people)) return;
      if (STYLES.includes(saved.style)) S.style = saved.style;
      for (const x of saved.people.slice(0, MAX - S.list.length)) {
        if (!(x.blob instanceof Blob)) continue;
        S.list.push({ blob: x.blob, w: x.w, h: x.h, url: URL.createObjectURL(x.blob), name: x.name || '', id: x.id || null, state: x.id ? 'ready' : 'local', error: '' });
      }
      paint(); onChange('restore', S.list.length);
    }
    return { mount, setLook, add, sync, check, ready, body, lost, clear, save, restore, count: () => S.list.length };
  }
  return { create, later, STYLES, LABEL, AUTO, MAX, NAME_MAX };
})();
