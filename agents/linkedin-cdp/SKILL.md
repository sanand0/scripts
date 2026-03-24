---
name: linkedin-cdp
description: Navigate LinkedIn via Chrome DevTools Protocol (CDP) using `uvx rodney` connected to an existing logged-in browser session. Use for extracting profile information, discovering people by city/role/interest, finding people who can help with specific tasks, and surfacing interesting posts and content.
argument-hint: "[task or query]"
---

# LinkedIn CDP Skill

Navigate LinkedIn via Chrome DevTools Protocol using `uvx rodney` connected to an existing logged-in browser session.

## Critical Constraints

1. **Tab indices are volatile.** They shift whenever any tab opens or closes. Never store an index across commands — always re-discover with `pages | grep linkedin` before use.

2. **Use `window.location.href` not `rodney open`.** `rodney open` on a LinkedIn tab can cause the navigation to land in a new tab while the original tab becomes `edge://newtab/`, leaving the active index pointing nowhere useful.

3. **Always verify after navigation.** After navigating, check `pages` again to find the new index of the LinkedIn tab before running `js`.

4. **Cookie presence ≠ authenticated.** `JSESSIONID` in `document.cookie` is necessary but not sufficient — the page content can still be a login screen. A tab restored after a browser crash often has the cookie but serves stale cached content; navigating away then redirects to login. Always confirm the visible page is actually LinkedIn content, not a login overlay.

5. **Parallel agents break each other** unless each uses a distinct `RODNEY_HOME`. Use `RODNEY_HOME=/tmp/rodney-N` per agent. But even with isolation, both agents still share the same underlying browser — JS execution runs on whichever page each agent's `active_page` index points to, which can shift if the other agent navigates.

6. **`rodney js` is ES5 only**: no `const`/`let`, no `?.`, no template literals. Use `var` and `el ? el.x : null`.

7. **`rodney js` times out at ~30s**: don't `fetch()` paginated API endpoints inline. Read from BPR cache instead.

8. **Complex JS → write to file**: `$(cat /tmp/script.js)` avoids shell quoting issues with apostrophes and special characters.

9. **`li_at` cookie is session-bound**: all LinkedIn API calls must be made via `rodney js fetch()` inside the browser — `curl` returns 302/400.

10. **BPR cache only exists on own/1st–2nd degree profiles**: public-only or distant profiles (e.g. Satya Nadella) render without it; fall back to DOM.

---

## Setup

```bash
# Isolate rodney state (required if running multiple agents)
export RODNEY_HOME=/tmp/rodney-$$

# Connect and find LinkedIn
uvx rodney connect localhost:9222
uvx rodney pages 2>&1 | grep -i "linkedin.com"
# Pick the feed tab (title starts with "(N) Feed | LinkedIn"), e.g. [5]

# Verify session — check BOTH cookie and visible content
uvx rodney page 5
uvx rodney js "document.cookie.indexOf('JSESSIONID') >= 0 ? 'cookie:OK' : 'LOGGED_OUT'" 2>&1
uvx rodney js "window.location.href.indexOf('login') >= 0 ? 'REDIRECT:login' : document.title" 2>&1
# If title shows feed and URL has /feed/ → safe to proceed
```

**Login-redirect recovery:** If any navigation lands on `login?` or `uas/login`:

1. Re-find the feed tab with `pages | grep "Feed.*LinkedIn"`
2. Switch to it and confirm `document.title` shows the feed (not a login page)
3. Navigate again from there
4. If it redirects again, the session has fully expired — ask the user to log back in manually, then reconnect

**Region domains:** LinkedIn may redirect to `sg.linkedin.com`, `it.linkedin.com`, etc. based on IP/locale. This breaks URL matching on `linkedin.com`. Grep for `linkedin.com` broadly, not just `www.linkedin.com`.

---

## Profile Extraction

```bash
# Navigate using JS (not rodney open)
uvx rodney js "window.location.href='https://www.linkedin.com/in/VANITYNAME/'" 2>&1
uvx rodney sleep 3

# Re-find the tab (index will have changed)
LI=$(uvx rodney pages 2>&1 | grep 'linkedin.com/in/' | grep -o '\[[0-9]*\]' | tr -d '[]' | head -1)
uvx rodney page $LI
```

### BPR Cache (structured, fast — own/1st/2nd-degree only)

```bash
cat > /tmp/li_profile.js << 'EOF'
(function() {
  var person = null;
  document.querySelectorAll('code[id^="bpr-guid-"]').forEach(function(el) {
    try {
      var dl = document.querySelector('#datalet-' + el.id);
      if (!dl) return;
      var req = JSON.parse(dl.textContent);
      if (req.request && req.request.indexOf('voyagerIdentityDashProfiles') >= 0) {
        var d = JSON.parse(el.textContent);
        person = (d.included || []).find(function(i) { return i.lastName; });
      }
    } catch(e) {}
  });
  if (!person) return JSON.stringify({error: 'no BPR', name: (document.querySelector('h1')||{}).textContent});
  return JSON.stringify({
    name: person.firstName + ' ' + person.lastName,
    headline: person.headline,
    vanity: person.publicIdentifier,
    urn: person.entityUrn,
    premium: person.premium,
    creator: person.creator,
    geoUrn: person.geoLocation ? person.geoLocation['*geo'] : null
  }, null, 2);
})()
EOF
uvx rodney js "$(cat /tmp/li_profile.js)" 2>&1
```

### DOM Fallback (any profile)

```bash
uvx rodney js "(function() { var h1 = document.querySelector('h1'); var hl = document.querySelector('.text-body-medium.break-words'); return JSON.stringify({name: h1 ? h1.textContent.trim() : null, headline: hl ? hl.textContent.replace(/\s+/g,' ').trim() : null}); })()" 2>&1
```

---

## People Search

**Search results are the most reliable data source.** Profile page navigation is flaky (login overlays, incomplete states, redirects). For name, headline, location, and connection degree, the search snippet is sufficient and far more stable. Prefer collecting from search results and only visit profiles when you need data not available in the snippet.

Navigate directly by URL — all filter combinations work via query params:

```
/search/results/people/?keywords=QUERY
  &network=["F"]            # 1st connections only (F=1st, S=2nd)
  &geoUrn=["urn:li:geo:ID"] # city/country filter
  &currentCompany=["URN"]   # company filter
  &page=2                   # pagination (10/page, ~10 pages max free)
```

**Geo URNs:** Singapore `103804675` · Bangalore `105556990` · Mumbai `104442216` · India `102713980` · USA `103644278`

```bash
uvx rodney js "window.location.href='https://www.linkedin.com/search/results/people/?keywords=AI+researcher&network=%5B%22F%22%2C%22S%22%5D&geoUrn=%5B%22urn%3Ali%3Ageo%3A103804675%22%5D'" 2>&1
uvx rodney sleep 3
LI=$(uvx rodney pages 2>&1 | grep 'Search.*LinkedIn' | grep -o '\[[0-9]*\]' | tr -d '[]' | head -1)
uvx rodney page $LI
```

### Extract Results

Search results: `para[0]` = "Name • 2nd", `para[1]` = headline, `para[2]` = location.

```bash
cat > /tmp/li_search.js << 'EOF'
(function() {
  var items = document.querySelectorAll('[data-testid="lazy-column"] [role="listitem"]');
  if (!items.length) items = document.querySelectorAll('[role="list"] [role="listitem"]');
  var out = [];
  items.forEach(function(item) {
    var link = item.querySelector('a[href*="/in/"]');
    var img = item.querySelector('img[alt]');
    var paras = Array.from(item.querySelectorAll('p')).map(function(p) {
      return p.textContent.replace(/\s+/g,' ').trim();
    }).filter(function(t) { return t && t.length > 2; });
    out.push({
      url: link ? link.href.split('?')[0] : null,
      name: img ? img.alt.replace(/ profile photo.*/, '').trim() : null,
      headline: paras[1] || null,   // para[0] is "Name • degree"
      location: paras[2] || null,
      degree: (paras[0] || '').match(/[•·]\s*(\w+)/) ? (paras[0] || '').match(/[•·]\s*(\w+)/)[1] : null
    });
  });
  return JSON.stringify(out, null, 2);
})()
EOF
uvx rodney js "$(cat /tmp/li_search.js)" 2>&1
```

---

## Feed & Content

```bash
uvx rodney js "window.location.href='https://www.linkedin.com/feed/'" 2>&1
uvx rodney sleep 3
# re-find and switch to the feed tab, then:
```

```bash
cat > /tmp/li_feed.js << 'EOF'
(function() {
  var posts = document.querySelectorAll('[data-urn][role="article"]');
  if (!posts.length) { window.scrollTo(0,200); return JSON.stringify({status:'scrolled, retry'}); }
  var out = [];
  posts.forEach(function(post) {
    var urn = post.getAttribute('data-urn');
    var img = post.querySelector('img[alt]');
    var link = post.querySelector('a[href*="/in/"]');
    var parts = [];
    post.querySelectorAll('span[dir="ltr"], p[dir="ltr"]').forEach(function(el) {
      var t = el.textContent.replace(/\s+/g,' ').trim();
      if (t) parts.push(t);
    });
    var reactions = post.querySelector('[aria-label*="reaction"], .social-details-social-counts__reactions-count');
    out.push({
      urn: urn,
      url: 'https://www.linkedin.com/feed/update/' + urn + '/',
      author: img ? img.alt.replace(/ profile photo.*/, '').trim() : null,
      profile: link ? link.href.split('?')[0] : null,
      text: parts.join(' ').slice(0, 400),
      reactions: reactions ? reactions.textContent.trim() : null
    });
  });
  return JSON.stringify(out, null, 2);
})()
EOF
uvx rodney js "$(cat /tmp/li_feed.js)" 2>&1
```

**Content search by hashtag:** `/search/results/content/?keywords=%23HASHTAG`
**Posts by person:** `/in/VANITYNAME/recent-activity/all/` — prefer this over full profile pages for understanding someone's interests and writing style; it's more reliably structured and loads without auth issues that affect profile pages.
**Scroll for more:** `uvx rodney js "window.scrollTo(0, document.body.scrollHeight)" && uvx rodney sleep 2`

---

## SPA Pages & Text Extraction

LinkedIn is a JavaScript SPA — most pages render content after load. **`outerHTML` only captures the static shell; use `document.body.innerText` to get rendered text.**

```bash
uvx rodney js "document.body.innerText" 2>&1 > /tmp/page_text.txt
```

Save raw extracts to temp files immediately after visiting a page — avoids re-visiting if processing fails later:

```bash
uvx rodney js "document.body.innerText" 2>&1 > /tmp/li_raw_$(date +%s).txt
```

**Analytics URLs** (widely useful for any account analytics work):
- Content analytics: `/analytics/creator/content/?timeRange=past_365_days`
- Audience analytics: `/analytics/creator/audience/?timeRange=past_365_days`
- Individual post: `/analytics/post-summary/urn:li:activity:URN/`
- `?timeRange=` accepts: `past_7_days`, `past_30_days`, `past_90_days`, `past_365_days`

---

## Connections & Network

```bash
# My connections
uvx rodney js "window.location.href='https://www.linkedin.com/mynetwork/invite-connect/connections/'" 2>&1
uvx rodney sleep 3
# re-find tab, then extract links with non-empty text (skip the image-only links):
uvx rodney js "(function() { var seen = {}; var r = []; Array.from(document.querySelectorAll('a[href*=\"/in/\"]')).forEach(function(a) { var href = a.href.split('?')[0]; var text = a.textContent.replace(/\s+/g,' ').trim(); if (text && !seen[href]) { seen[href] = true; r.push({url: href, text: text.slice(0,150)}); } }); return JSON.stringify(r.slice(0,20), null, 2); })()" 2>&1
```

**1st-degree search:** add `&network=%5B%22F%22%5D` to any search URL
**People You May Know:** `/mynetwork/`
**Company employees:** `/company/NAME/people/`

---

## Voyager API (in-browser only)

```bash
cat > /tmp/li_api.js << 'EOF'
(function() {
  var m = document.cookie.match(/JSESSIONID="(ajax:[^"]+)"/);
  if (!m) return 'no session';
  return fetch('/voyager/api/me', {
    credentials: 'include',
    headers: {'csrf-token': m[1], 'X-RestLi-Protocol-Version': '2.0.0', 'Accept': 'application/vnd.linkedin.normalized+json+2.1'}
  }).then(function(r) { return r.text(); });
})()
EOF
uvx rodney js "$(cat /tmp/li_api.js)" 2>&1 | jaq '.included[0] | {name: (.firstName+" "+.lastName), headline}'
```

Key endpoints: `/voyager/api/me` · `/voyager/api/relationships/connectionsSummary` · `/voyager/api/graphql?variables=(vanityName:X)&queryId=voyagerIdentityDashProfiles.34ead06db82a2cc9a778fac97f69ad6a`

---

## Parallel Agent Pattern

```bash
# Each agent gets isolated rodney state but shares the browser
RODNEY_HOME=/tmp/rodney-A uvx rodney connect localhost:9222
RODNEY_HOME=/tmp/rodney-A uvx rodney newpage "https://www.linkedin.com/in/person1/"
# work in that tab...

RODNEY_HOME=/tmp/rodney-B uvx rodney connect localhost:9222
RODNEY_HOME=/tmp/rodney-B uvx rodney newpage "https://www.linkedin.com/in/person2/"
# work in that tab...
# Each agent tracks its own active_page independently
```

`RODNEY_HOME` isolates the state file. Combined with `newpage`, each agent works in its own tab with no index conflicts. Close tabs with `rodney closepage INDEX` when done.

---

## Anti-Bot Notes

- Sleep 2–5s between navigations; LinkedIn fingerprints timing patterns
- `/checkpoint/` in URL = CAPTCHA wall — stop immediately, wait 30+ min
- Profile views notify the target (they see who viewed)
- Free account: ~10 search pages × 10 results; ~300 profile views/month before commercial use limit
- Session survives browser restarts if cookies are preserved — but navigating to new pages may invalidate it if the session is stale (browser crash case)
