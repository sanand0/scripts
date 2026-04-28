# htmlemail

<!--

cd /home/sanand/code/scripts
dev.sh -v /home/sanand/code/blog:/home/sanand/code/blog:ro
codex --yolo --model gpt-5.5 --config model_reasoning_effort=low

-->

## Generalize, 28 Apr 2026

<!-- https://chatgpt.com/c/69f0c0c1-6200-83ea-8df1-87cd33e53da8 -->

Refactor the provided single-file Python script `htmlemail.py` into a generic portable CLI that can be run with:

```bash
uv run https://raw.githubusercontent.com/sanand0/scripts/main/htmlemail.py ...
```

Keep it as one PEP 723-compatible script with inline dependencies. Do not package it.

Requirements:

1. Add `platformdirs` and store all persistent app state under the platform-appropriate user config directory for app name `htmlemail`.
   - Use a config file: config.json.
   - Store OAuth client secrets at `<config_dir>/credentials.json`.
   - Store tokens under `<config_dir>/tokens/`.
   - Never require `credentials.json` or `token.json` in the current working directory.

2. Add CLI options:
   - `--init --client-secrets PATH`: copy the Google OAuth desktop client secrets JSON into the config dir.
   - `--show-config`: print config dir, credentials path, and known sender profiles.
   - `--from EMAIL`: select/create the OAuth token profile for that sender.
   - `--logout-from EMAIL`: delete that sender’s saved token/profile.
   - `--base-url URL`: base URL used to resolve relative links.
   - Keep `--email` and `--cc` repeatable.
   - Keep `--test`.
   - Optionally keep `--token` only as a deprecated override, but normal operation must use `--from`.

3. OAuth behavior:
   - Use scopes: `openid`, `email`, `profile`, and `https://www.googleapis.com/auth/gmail.send`.
   - Remove Gmail readonly and People API usage.
   - After OAuth, obtain the authenticated Google identity from the OIDC token/userinfo data.
   - Verify that authenticated email equals `--from` case-insensitively. If not, fail with a clear error and do not send.
   - Save one token file per sender. Generate safe token filenames from normalized email plus an 8-character sha256 suffix.
   - Store sender profile metadata in config.json: requested email, verified email, Google sub, display name if available, relative token path, created/updated timestamps, and scopes fingerprint.
   - If scopes fingerprint changes, force re-auth for that sender.

4. Rendering behavior:
   - Remove hard-coded `https://www.s-anand.net/blog/{slug}/`.
   - Determine base URL in this order: CLI `--base-url`, frontmatter `base_url`, frontmatter `canonical_url`, frontmatter `url`, else None.
   - If base URL is None, do not rewrite relative links; emit a warning to stderr if relative href/src values exist.
   - Keep YouTube iframe replacement, media replacement, markdown tables, syntax highlighting, premailer CSS inlining.

5. Sending behavior:
   - Build only the Gmail API service.
   - Use the authenticated email as the actual From email.
   - Use the OIDC/profile display name if available; otherwise use the email address.
   - Do not attempt to spoof arbitrary From headers.
   - Send progress/warnings to stderr, never contaminate HTML stdout.

6. Tests:
   - Update inline tests so they no longer assume s-anand.net.
   - Add tests for base-url resolution, no-base-url behavior, token filename sanitization, config path creation, config load/save, and sender mismatch detection with mocked identity.
   - Ensure `--test` passes without requiring Google credentials.
   - You can use /home/sanand/code/blog/{credentials.json,token*.json} to test by sending emails to root.node@gmail.com / s.anand@gramener.com

Preserve existing useful behavior and comments. Keep the implementation simple, typed, readable, and robust on Linux/macOS/Windows.

---

<!-- /effort medium -->

I ran `htmlemail.py --from root.node@gmail.com --email s.anand@gramener.com README.md` and it reported:

Warning: Scope has changed from "email openid profile https://www.googleapis.com/auth/gmail.send" to "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.send".

Why does this happen? Is there a minimal, elegant fix to it? If yes, fix it. Else, explain and ask me.

<!-- codex resume 019dd48c-fbe2-7083-ae39-b672dcfaaae5 --yolo -->
