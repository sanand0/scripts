import * as duckdb from "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.30.0/+esm";
const bundles = duckdb.getJsDelivrBundles();
const bundle = await duckdb.selectBundle(bundles);
const worker_url = URL.createObjectURL(
  new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }),
);
const worker = new Worker(worker_url);
const logger = new duckdb.ConsoleLogger();
const db = new duckdb.AsyncDuckDB(logger, worker);
await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
const conn = await db.connect();
await conn.query(`CREATE TABLE posts (post_id INTEGER, username VARCHAR, timestamp TIMESTAMP, comments JSON);`);
await db.registerFileText("rows.json", JSON.stringify(rows));
await conn.insertJSONFromPath("rows.json", { name: "rows" });
await conn.query(`INSERT INTO posts SELECT post_id, username, timestamp, comments FROM rows;`);
await conn.query("INSTALL json; LOAD json;");
const response = await conn.query(sql);
await conn.close();
const result = response.toArray().map((row) => row.toJSON());
