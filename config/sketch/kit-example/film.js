// For: whoever changes sketch/kit.js; a plain reference sheet of every piece, clean then crayon
/* Kit gallery: eight 3-second pages, each a group of kit pieces entering on its own clock. The
   first 24 s are the clean look on the white ground, the next 24 s the same pages in crayon on
   paper. scripts/check-kit.py renders it and fails on any error the page reports. */
SK.setStyle('clean');
SK.setGround('white');
const P = 3; // seconds a page
const pageT = (t) => t % P; // each page's own clock

const PAGES = [
  // 0 -- text: title, pills, label, para, counter
  (t, t0) => {
    SK.title('Close your month in minutes', -820, -430, { kicker: 'Launch', sub: 'Snap a receipt, and the books file themselves.', accent: 'minutes', t: t0, size: 84 });
    SK.pill('NEW', -820, -60, { align: 'left', icon: 'star', in: { t: t0 + .4, type: 'pop' } });
    SK.pill('Auto-sized chip', -600, -60, { align: 'left', fill: '#eef1fd', col: '#2f6fdb', in: { t: t0 + .55, type: 'pop' } });
    SK.label('Static label, fitted to 360 wide: a long line that shrinks', -820, 40, { size: 40, maxW: 700, align: 'left' });
    SK.para('A paragraph wraps inside its width and types itself on, line after line, from its start time.', -820, 110, { w: 700, size: 34, t: t0 + .3, cps: 60 });
    SK.counter(500, -250, { from: 0, to: 128450, t0: t0 + .2, t1: t0 + 1.8, fmt: 'money', size: 110 });
    SK.counter(500, -90, { from: 0, to: 97, t0: t0 + .2, t1: t0 + 1.8, fmt: 'pct', size: 90, col: '#2f9e5b' });
    SK.counter(500, 50, { from: 0, to: 754, t0: t0, t1: t0 + 2, fmt: 'mm:ss', size: 80 });
    SK.label('Привіт, кириличний текст', 500, 180, { size: 44 });
    SK.lowerThird('Ada Lovelace', 'Founder, Analytical Engines', { t: t0 + .3 });
  },
  // 1 -- checklist, cross, callout, quote, marks
  (t, t0) => {
    SK.checklist([{ text: 'Snap the receipt', t: t0 + .1 }, { text: 'Match the statement', t: t0 + .5, sub: 'six of six lines' }, { text: 'Spreadsheets', t: t0 + .9, mark: 'cross' }, { text: 'Numbered step', t: t0 + 1.2, mark: 2 }], -860, -420, { w: 640 });
    SK.cross(-760, 200, 40, Math.min(1, (t - t0) / .6));
    SK.check(-660, 200, 40, Math.min(1, (t - t0) / .6));
    SK.callout('the engine', 150, -300, 420, -400, { t: t0 + .2, ring: 40 });
    SK.callout('a pill callout', 150, -150, 420, -120, { t: t0 + .5, pill: true });
    SK.quote('A shared library does stop re-invention.', 'the harvest, 2026-10-01', 330, 200, { w: 900, t: t0 + .3, size: 46 });
    SK.underline(-860, -420 + 0, 420, { in: { t: t0 + 1, d: .4 } });
    SK.circle(-760, 200, 70, 60, { in: { t: t0 + 1.2, d: .5 } });
    SK.arrow(-500, 380, -200, 300, { in: { t: t0 + 1.4, d: .5 } });
    SK.dimension(-160, 420, 260, 420, '42 cm', { t: t0 + .8 });
  },
  // 2 -- bars, chart
  (t, t0) => {
    SK.label('Bars and a line', -820, -460, { size: 40, wt: 800, align: 'left' });
    SK.bars([{ label: 'Jan', value: 12 }, { label: 'Feb', value: 19 }, { label: 'Mar', value: 27 }, { label: 'Apr', value: 41 }], -860, -380, { w: 760, h: 520, t: t0 + .1, highlight: 3 });
    SK.bars([{ label: 'Old', value: 14.5 }, { label: 'New', value: 3.2 }], 160, -360, { w: 640, h: 200, dir: 'h', t: t0 + .2, post: ' min', dec: 1 });
    SK.chart([3, 4, 3.6, 5, 6.2, 5.8, 7.4, 9.1], 160, -40, { w: 700, h: 380, t: t0 + .2, d: 1.6, grid: 3, end: '+38%', labels: ['2019', '2026'] });
  },
  // 3 -- donut, units, meter, ring, stat
  (t, t0) => {
    SK.donut([{ value: 52, label: 'Rent' }, { value: 23, label: 'Food' }, { value: 15, label: 'Travel' }, { value: 10, label: 'Fun' }], -640, -180, 210, { t: t0 + .1, centre: '$2,480' });
    SK.units(37, 100, -860, 170, { cols: 20, size: 30, t: t0 + .2 });
    SK.meter(.72, 150, -400, 700, { t: t0 + .1, label: 'Uploaded', value: true });
    SK.ring(.64, 300, -130, 120, { t: t0 + .2, text: true });
    SK.stat(640, -130, { kicker: 'Saved', value: 14, post: ' h', caption: 'every month, per team', icon: 'clock', t: t0 + .3, w: 400 });
    SK.stat(420, 280, { kicker: 'Customers', value: 12480, caption: 'in 40 countries', icon: 'users', t: t0 + .5, w: 460 });
  },
  // 4 -- steps, timeline, flow
  (t, t0) => {
    SK.steps(['Order', 'Sort', 'Truck', 'Deliver'], -800, -400, { w: 1000, times: [t0, t0 + .7, t0 + 1.4, t0 + 2.1] });
    SK.timeline([{ at: 1817, label: '1817', sub: 'running machine', t: t0 + .2 }, { at: 1885, label: '1885', sub: 'safety bicycle', t: t0 + .5 }, { at: 1970, label: '1970', sub: 'BMX', t: t0 + .8 }, { at: 2010, label: '2010', sub: 'e-bikes', t: t0 + 1.1 }], -820, -40, { w: 1640, ticks: [1800, 1900, 2000], alt: true, t: t0 });
    SK.flow([{ id: 'a', x: -500, y: 330, label: 'You', icon: 'user', t: t0 + .2 }, { id: 'b', x: 0, y: 330, label: 'Agent', icon: 'bolt', t: t0 + .5 }, { id: 'c', x: 500, y: 230, label: 'Search', icon: 'search', t: t0 + .8 }, { id: 'd', x: 500, y: 430, label: 'Email', icon: 'mail', t: t0 + 1 }], [['a', 'b'], ['b', 'c', { bow: -20 }], ['b', 'd', { bow: 20, label: 'sends' }]], { dots: 2 });
  },
  // 5 -- window, phone, chat, cursor, button, field
  (t, t0) => {
    SK.window(-900, -460, 820, 560, { url: 'kitcut.ai/film', title: 'KitCut', content: (x0, y0, w) => {
      SK.field('a 30 second launch film', x0 + 40, y0 + 80, w - 80, { t: t0 + .2, label: 'Your idea' });
      SK.button('Make the film', x0 + w / 2, y0 + 260, { press: t0 + 2.2, icon: 'play' });
    } });
    const cur = SK.cursorPath([[t0, -100, 300], [t0 + 1.8, -500, 0], [t0 + 2.6, -500, 0]]);
    const [cx, cy] = cur(t); SK.cursor(cx, cy, { click: t0 + 2.2 });
    SK.phone(520, 20, { s: 1.15, screen: (x0, y0, w, h) => {
      SK.label('Messages', x0 + w / 2, y0 + 80, { size: 30, wt: 700, col: '#111' });
      SK.chat([{ who: 'them', text: 'Is the film ready?', t: t0 + .4 }, { who: 'me', text: 'Rendering now, two minutes.', t: t0 + 1.2 }, { who: 'them', text: 'Great!', t: t0 + 2.3 }], x0 + 20, y0 + 130, { w: w - 40, h: h - 170, size: 24 });
    } });
    SK.toast('Your film is ready', '30 s, 1080p', 0, -440, { t: t0 + .6, until: t0 + 2.6, icon: 'check', app: 'KITCUT' });
  },
  // 6 -- code, icons, logo, pulse, particles, glow
  (t, t0) => {
    SK.code(['$ npm run film', '# rendering 28,800 frames', '> done in 9:12', '$ open film.mp4'], -900, -440, { w: 800, t: t0 + .1, title: 'terminal', cps: 40 });
    SK.ICONS.forEach((k, i) => SK.icon(k, -860 + (i % 10) * 82, 60 + Math.floor(i / 10) * 82, 24, { in: { t: t0 + .02 * i, type: 'pop' } }));
    SK.logo('logo', 420, -300, { w: 360, h: 140, plate: '#ffffff', in: { t: t0 + .2, type: 'pop' } });
    SK.glow(420, 160, 260, '#ffd76a', { alpha: .8 });
    SK.particles({ x: 420, y: 160, t0, rate: 50, life: 1.4, speed: [160, 360], spread: 1.2, col: ['#2f6fdb', '#ffd76a', '#d64545', '#2f9e5b'], shape: 'confetti', seed: 3 });
    SK.pulse(760, 380, t0, { every: 1.2 });
    SK.icon('bell', 760, 380, 26, { col: '#fff', bg: '#d64545' });
  },
  // 7 -- end card
  (t, t0) => {
    SK.endCard({ logo: 'logo', title: 'Make films from a sentence', tagline: 'Drawn, narrated and scored in minutes', url: 'kitcut.ai', cta: 'Try it free', t: t0 + .1, bg: '#14171f', accent: '#2f6fdb' });
  },
];

SK.film({
  duration: 48,
  camera: SK.breath(SK.camera([[0, [0, 0, 1]]]), { amp: 6, zoom: .01 }),
  fadeOut: 0,
  draw(t) {
    const crayon = t >= 24, k = Math.floor((t % 24) / P), t0 = t - pageT(t);
    if (crayon) { SK.setStyle('crayon'); SK.setGround('paper'); } else { SK.setStyle('clean'); SK.setGround('white'); }
    SK.at(0, 0, 0, 1, () => PAGES[k](t, t0));
  },
});
