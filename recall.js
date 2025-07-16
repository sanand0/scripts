#!/usr/bin/env -S deno run --allow-read --allow-env

/* Helps practice spaced recall from my notes.

Usage:

recall.js | glow

This automatically picks the latest files matching EITHER:

- "llm" (@llms.md), OR
- "til" (@til-things-i-learned.md)

... and prints a random top-level bullet (preferring recent ones).

*/

import { unified } from "npm:unified";
import remarkParse from "npm:remark-parse";
import remarkStringify from "npm:remark-stringify";
import { visit } from "npm:unist-util-visit";

// args & paths
const terms = Deno.args.length ? Deno.args : ["llm", "til"];
const term = terms[Math.floor(Math.random() * terms.length)];
const re = new RegExp(term, "i");

const HOME = Deno.env.get("HOME") ?? Deno.env.get("USERPROFILE") ?? "";
const DIR = `${HOME}/Dropbox/notes`;

// pick newest matching .md file
const files = [];
for await (const e of Deno.readDir(DIR))
  if (e.isFile && e.name.endsWith(".md") && re.test(e.name))
    files.push({ path: `${DIR}/${e.name}`, mtime: (await Deno.stat(`${DIR}/${e.name}`)).mtime?.getTime() || 0 });

files.sort((a, b) => b.mtime - a.mtime);
const txt = await Deno.readTextFile(files[0].path);

// parse markdown, collect top‑level list items
const tree = unified().use(remarkParse).parse(txt);
const items = [];
visit(tree, "list", (node, _, parent) => {
  if (parent.type === "root") node.children.forEach((li) => items.push(li));
});

// spaced‑recall random: weight ∝ 1/(index+1)
const weights = items.map((_, i) => 1 / (i + 1));
const pick = (r, acc = 0) => items.find((_, i) => (acc += weights[i]) >= r);
const choice = pick(Math.random() * weights.reduce((a, b) => a + b));

// stringify the chosen bullet & render to terminal
const md = unified().use(remarkStringify).stringify(choice);
console.log(md);
console.log("Source:", files[0].path);
