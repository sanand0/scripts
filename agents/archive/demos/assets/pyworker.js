import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.mjs";

const pyodideReadyPromise = loadPyodide();

self.onmessage = async (event) => {
  // make sure loading is done
  const pyodide = await pyodideReadyPromise;
  const { id, code, data, context } = event.data;

  // Now load any packages we need
  await pyodide.loadPackagesFromImports(code);
  // Change the globals() each time
  const dict = pyodide.globals.get("dict");
  const serialize = (val) => {
    if (val === undefined) return null;
    try {
      return JSON.parse(JSON.stringify(val));
    } catch (err) {
      return val;
    }
  };
  const contextEntries = Object.entries(context || {}).map(([key, value]) => [key, pyodide.toPy(serialize(value))]);
  const globals = dict(contextEntries);
  globals.set("data", pyodide.toPy(data));
  try {
    const resultProxy = await pyodide.runPythonAsync(code, { globals });
    const result = resultProxy.toJs({ dict_converter: Object.fromEntries });
    resultProxy.destroy?.();
    self.postMessage({ id, result });
  } catch (e) {
    self.postMessage({ id, error: e.message });
    return;
  }
};
