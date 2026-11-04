# grok-imagine

Pictures for a still film (`scripts/still-film.py`) made in Grok Imagine (grok.com/imagine) by
driving the page's own DOM through the Claude browser extension: no screenshots, no clicks by
coordinate, and no tool call per picture. A queue in the page makes one picture per scene and
hands each to a local receiver that writes `<out>/<scene id>.jpg`.

Not part of the `scripts/` pipeline (a browser half and a stdlib server), so it skips the `_env`
and check-script conventions on purpose.

## Where it runs

On **kc-local**, in the Edge of the `VideoMakers_io` profile (the "Linux" browser in
`list_connected_browsers`, screen :101), which is signed in to Grok. The receiver must run on the
same machine as that browser, because the page reaches it at `127.0.0.1:8899`.

## Use

```bash
python3 -I tools/grok-imagine/receiver.py --out projects/<id>/images      # leave running
```

In the Grok tab (javascript tool), install the runner, which the receiver serves:

```js
const w = window.open('http://127.0.0.1:8899/recv.html','sfrecv','width=360,height=240');
await new Promise(r=>setTimeout(r,1500));
const text = await new Promise(res=>{ addEventListener('message',e=>{ if(e.data?.kind==='still-film-lib') res(e.data.text) }); w.postMessage({kind:'still-film-lib'},'*'); });
localStorage.setItem('sf_lib', text); eval(text); 'installed'
```

After a reload, `eval(localStorage.getItem('sf_lib'))` is enough. Then:

```js
SF.config({prefix: '<style text>', castPrompt: '<cast text>', aspect: '16:9', width: 1792});
SF.setRef('style', '<data: URL of the style sheet>');   // stored in localStorage, once
SF.setRef('cast',  '<data: URL of the cast line-up>');
SF.add([{name:'s001', scene:'...', cast:true}, ...]);
SF.start();          // returns at once; the loop runs in the page
SF.status();         // {running, current, left, done, failed, log}
```

Reference pictures come through the receiver: start it with `--refs <folder>` and call
`await SF.loadRef('style', 'style-ref.jpg')` / `await SF.loadRef('cast', 'cast.jpg')` (file names
inside that folder) instead of `setRef`.

## What each job does

1. Goes back to the composer through the page's own `/imagine` link (an in-app navigation, so the
   runner survives), sets the Aspect Ratio menu to 16:9.
2. Attaches the references (style, plus the cast sheet when `cast:true`) to the multiple file input
   and waits 4.5 s (submitting sooner drops them).
3. Types prefix + cast prompt + `Scene: ...` with `execCommand('insertText')`, presses Enter.
4. Waits for the new post id in the URL and picks the image under `/generated/<post id>/` that is
   1792 px wide (the page also holds thumbnails of earlier pictures).
5. Fetches it with credentials and posts it to the receiver popup, which POSTs it to receiver.py.
   An existing picture is kept as `<id>_old.jpg`.
6. A failure is retried once at the back of the queue, then listed in `failed`.

## Traps

- grok.com's CSP blocks a fetch to 127.0.0.1, and Chrome blocks a site's repeated downloads (the tab
  freezes). The popup + postMessage route avoids both.
- The Grok tab must be the active tab of its window: a background tab stops rendering and the loop
  waits forever.
- A cookie banner on a fresh profile can swallow the upload; dismiss it ("Reject All") first.
- Grok rate-limits image making after heavy use (errors, then nothing); wait ~40 minutes.
