// Web Worker: runs the unmodified Milestone 2 simulator (Python) inside Pyodide.
// Messages in:  {id, op: 'simulate' | 'mc' | 'access', cfg, n}
// Messages out: {id, ok, result} | {id, progress} | {status}
importScripts('pyodide/pyodide.js');

let py = null;
const ready = (async () => {
  postMessage({ status: 'loading' });
  // The standard library ships as base64 text (the artifact host does not serve .zip files)
  const b64 = await (await fetch(new URL('pyodide/python_stdlib.b64.txt', self.location))).text();
  const raw = atob(b64.trim());
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  const stdLibURL = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }));
  py = await loadPyodide({ indexURL: new URL('pyodide/', self.location).href, stdLibURL });
  const bundle = await (await fetch(new URL('data/py_bundle.json', self.location))).json();
  py.FS.mkdirTree('/app/milestone2/sim');
  py.FS.mkdirTree('/app/info');
  for (const [name, src] of Object.entries(bundle.py)) py.FS.writeFile('/app/milestone2/sim/' + name, src);
  py.globals.set('ORB_JSON', bundle.data['orbital_elements.json']);
  py.globals.set('NET_JSON', bundle.data['network_model.json']);
  // geom.py reads info/data.zip relative to the repository root, so rebuild that zip in the virtual FS
  py.runPython(`
import sys, zipfile, json
with zipfile.ZipFile('/app/info/data.zip', 'w') as z:
    z.writestr('orbital_elements.json', ORB_JSON)
    z.writestr('network_model.json', NET_JSON)
sys.path.insert(0, '/app/milestone2/sim')
import webapi
`);
  postMessage({ status: 'ready', version: py.version });
})().catch((e) => postMessage({ status: 'error', error: String(e) }));

function call(expr, args) {
  py.globals.set('ARGS', JSON.stringify(args));
  return JSON.parse(py.runPython(`json.dumps(webapi.clean(${expr}))`));
}

onmessage = async (ev) => {
  const { id, op, cfg, n } = ev.data;
  try {
    await ready;
    if (!py) throw new Error('Python engine failed to start');
    if (op === 'simulate') {
      postMessage({ id, ok: true, result: call('webapi.simulate(json.loads(ARGS))', cfg) });
    } else if (op === 'mc') {
      const runs = [];
      const chunk = 5;
      for (let s = 1; s <= n; s += chunk) {
        const k = Math.min(chunk, n - s + 1);
        py.globals.set('ARGS', JSON.stringify(cfg));
        const r = JSON.parse(py.runPython(`json.dumps(webapi.clean(webapi.monte_carlo(json.loads(ARGS), ${k}, ${s})))`));
        if (!r.ok) throw new Error(r.error);
        runs.push(...r.runs);
        postMessage({ id, progress: runs.length / n });
      }
      postMessage({ id, ok: true, result: { runs } });
    } else if (op === 'access') {
      postMessage({ id, ok: true, result: call('webapi.access(**json.loads(ARGS))', cfg) });
    }
  } catch (e) {
    postMessage({ id, ok: false, error: String(e.message || e) });
  }
};
