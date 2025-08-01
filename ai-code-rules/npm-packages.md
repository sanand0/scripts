- Name packages as single words ("smartart"), joined words ("saveform") or hyphenated ("bootstrap-llm-provider")
- The main file name is package-name.js
- Use ESM ("type": "module")
- Use JavaScript, not TypeScript
- Encourage type definitions

## package.json

Include these keys:

- name: package-name
- version: semver
- description: 1-line (how it helps developers)
- homepage: typically "https://github.com/sanand0/repo#readme"
- repository: typically { type: "git", url: "https://github.com/sanand0/repo.git" }
- license: "MIT"
- author: typically "Anand S <root.node@gmail.com>"
- type: "module"
- prettier: { printWidth: 120 }
- files: [ "LICENSE", "README".md, "dist/" ]
- browser: "dist/package-name.min.js" if meant for browsers
- exports: "dist/package-name.min.js"
- bin: only for CLI apps
- scripts: typically includes:
  ```json
  {
    "build": "npx -y esbuild package-name.js --bundle --format esm --minify --outfile=dist/package-name.min.js",
    "lint:oxlint": "npx -y oxlint@1 --fix",
    "lint:js-md": "npx -y prettier@3.5 --print-width 120 --write '**/*.js' '!**/*.min.js' '!dist/**' '**/*.md'",
    "lint:html": "npx -y js-beautify@1 '**/*.html' --type html --replace --indent-size 2 --max-preserve-newlines 1 --end-with-newline",
    "lint": "npm run lint:oxlint && npm run lint:js-md && npm run lint:html",
    "test": "npx -y vitest@3 run --globals",
    "prepublishOnly": "npm run lint && npm run build && npm test"
  }
  ```
- dependencies: only if required
- devDependencies: only if required. Prefer `npx -y` in scripts over devDependencies. Used mainly if tests/utilities need packages, e.g. happy-dom, playwright, sharp
- peerDepedencies: only if required. E.g. { "bootstrap": "^5.3.7" }
- keywords: [ ... ]

## README.md

Include these H2 headings:

- Begin with shields, followed by a 1-line description of the package. Shields include
  ```markdown
  [![npm version](https://img.shields.io/npm/v/package-name.svg)](https://www.npmjs.com/package/package-name)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
  [![bundle size](https://img.shields.io/bundlephobia/minzip/package-name)](https://bundlephobia.com/package/package-name)
  ```
- Installation. Typically:

  ````markdown
  To use locally, install via `npm`:

  ```bash
  npm install package-name
  ```

  ... and add this to your script:

  ```js
  import { something } from "./node_modules/package-name/dist/package-name.js";
  ```

  To use via CDN, add this to your script:

  ```js
  import { something } from "https://cdn.jsdelivr.net/npm/package-name@1";
  ```
  ````

- Usage. Provide detailed examples covering all scenarios
  - API. Provide API documentation
- Development. Use this content:

  ```bash
  git clone https://github.com/user/package-name.git
  cd package-name

  npm install
  npm run lint && npm run build && npm test

  npm publish
  git commit . -m"$COMMIT_MSG"; git tag $VERSION; git push --follow-tags
  ```

- Release notes. This is a list of `[x.y.z](https://npmjs.com/package/package-name/v/x.y.y): dd mmm yyyy: Description of the change`
- License. Just mention `[MIT](LICENSE)`

## .gitignore

```
node_modules/
dist/
```
