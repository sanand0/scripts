// DuckDB usage
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
await conn.query(`CREATE TABLE posts (id INTEGER, name VARCHAR, timestamp TIMESTAMP, comments JSON);`);
await db.registerFileText("rows.json", JSON.stringify([
  { id: 1, name: "Post 1", timestamp: "2024-01-01T10:00:00Z", comments: [{ user: "alice", text: "Great post!" }] },
  { id: 2, name: "Post 2", timestamp: "2024-02-15T12:30:00Z", comments: [{ user: "bob", text: "Very informative." }] },
]));
await conn.insertJSONFromPath("rows.json", { name: "rows" });
await conn.query(`INSERT INTO posts SELECT id, name, timestamp, comments FROM rows;`);
await conn.query("INSTALL json; LOAD json;");

const response = await conn.query('SELECT * FROM posts');
await conn.close();
const result = response.toArray().map((row) => row.toJSON());
console.log(result);
