import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { variables, profileIdentifier, activityUrn, decodeProfile, decodeSearch, decodeUpdates, checkResponse, Cache, sync, archiveRecords, importArchive, importHistory, parseAnalytics, backup, run, parse, render, Client, searchFacets, sinceDate, syncAnalytics, mergeBackupRow, toBackupRow, exportBackupRows, writeBackupArchive, readBackupArchive, lockBackupArchive, selectBackupPosts, backupTimeFields, parseDetailedBackupAnalytics, parseBackupDemographics, applyBackupReplyParents } from '../linkedin';
const SCRIPT = fileURLToPath(new URL('../linkedin', import.meta.url));

test('identifiers and variables handle URLs, delimiter injection and non-LinkedIn hosts', () => {
  assert.equal(profileIdentifier('https://www.linkedin.com/in/example/?trk=foo'), 'example');
  assert.equal(activityUrn('https://www.linkedin.com/posts/example_topic-activity-1234567890123456789-abcd'), 'urn:li:activity:1234567890123456789');
  assert.throws(() => profileIdentifier('https://linkedin.com.evil/in/example/'));
  assert.throws(() => activityUrn('urn:li:member:123'));
  assert.equal(variables({ query: { keywords: 'a,b):List(x) 雪' }, values: ['urn:li:member:1'] }), '(query:(keywords:a%2Cb%29%3AList%28x%29%20%E9%9B%AA),values:List(urn%3Ali%3Amember%3A1))');
});

test('profile decoder follows target root, not the first referenced Profile', () => {
  const result = decodeProfile({ data: { '*elements': ['target'] }, included: [
    { entityUrn: 'other', $type: 'Profile', firstName: 'Wrong' },
    { entityUrn: 'target', $type: 'Profile', publicIdentifier: 'example', firstName: 'Example', lastName: 'Person', headline: 'Builder', '*industry': 'industry' },
    { entityUrn: 'industry', name: 'Software' },
  ] });
  assert.equal(result.id, 'target'); assert.equal(result.name, 'Example Person');
});

test('search decoder follows clusters and keeps result order without unrelated included entities', () => {
  const page = decodeSearch({ data: { data: { searchDashClustersByAll: { paging: { start: 0, count: 2, total: 10 }, elements: [{ items: [{ item: { '*entityResult': 'b' } }, { item: { '*entityResult': 'a' } }] }] } } }, included: [
    { entityUrn: 'noise', $type: 'EntityResultViewModel', title: { text: 'Wrong' }, navigationUrl: 'https://www.linkedin.com/in/wrong/' },
    { entityUrn: 'a', $type: 'EntityResultViewModel', title: { text: 'Alice' }, navigationUrl: 'https://www.linkedin.com/in/alice/' },
    { entityUrn: 'b', $type: 'EntityResultViewModel', title: { text: 'Bob' }, navigationUrl: 'https://www.linkedin.com/in/bob/' },
  ] }, 'people', { start: 0, count: 2 });
  assert.deepEqual(page.records.map(r => r.name), ['Bob', 'Alice']); assert.equal(page.next.start, 2);
});

test('activity root preserves token despite total zero and keeps post author separate from activity owner', () => {
  const page = decodeUpdates({ data: { data: { feedDashProfileUpdatesByMemberComments: { paging: { total: 0 }, metadata: { paginationToken: 'token' }, '*elements': ['u'] } } }, included: [
    { entityUrn: 'noise', $type: 'Update', metadata: { backendUrn: 'urn:li:activity:99' } },
    { entityUrn: 'u', $type: 'Update', metadata: { backendUrn: 'urn:li:activity:123' }, actor: { name: { text: 'Post author' } }, commentary: { text: { text: 'A post' } } },
  ] }, 'comments', { id: 'owner', name: 'Commenter' }, { start: 0, count: 1 });
  assert.equal(page.records.length, 1); assert.equal(page.next.token, 'token');
  assert.equal(page.records[0].actor.name, 'Commenter'); assert.equal(page.records[0].post.author.name, 'Post author');
  assert.equal(page.records[0].kind, 'activity');
});

test('changed schemas, logged-out HTML, challenges and rate limits produce actionable errors', () => {
  assert.throws(() => decodeProfile({ data: {}, included: [] }), e => e.code === 'SCHEMA_CHANGED');
  assert.throws(() => checkResponse({ status: 200, url: 'https://www.linkedin.com/login', contentType: 'text/html', body: '<html>Login</html>' }), e => e.code === 'AUTH_REQUIRED');
  assert.throws(() => checkResponse({ status: 403, url: 'https://www.linkedin.com/checkpoint/challenge', body: '' }), e => e.code === 'CHALLENGE_REQUIRED');
  assert.throws(() => checkResponse({ status: 429, body: '', retryAfter: '60' }), e => e.code === 'RATE_LIMITED' && e.retryAfter === 60);
});

const record = (id, text = 'Practical agents and databases') => ({ id, kind: 'post', text, name: 'Example', source: 'test' });

test('FTS updates, Unicode, literal punctuation, account isolation and richer fields survive partial reads', () => {
  const cache = new Cache(':memory:');
  cache.commit('a', 'feed', [record('1'), { ...record('2', '日本語 SQLite'), analytics: { saveCount: 7 } }], { start: 2 });
  cache.commit('b', 'feed', [record('1', 'Other account')], null);
  assert.equal(cache.search('a', 'agents').length, 1);
  assert.equal(cache.search('a', '日本語').length, 1);
  cache.commit('a', 'feed', [{ ...record('1', 'Updated post') }, record('2', 'New SQLite text')], null);
  assert.equal(cache.search('a', 'agents').length, 0);
  assert.equal(cache.get('a', '2').analytics.saveCount, 7);
  assert.equal(cache.search('a', 'Other').length, 0);
  assert.deepEqual(cache.search('a', '" OR * --'), []);
  cache.close();
});

test('page transaction rolls back records and checkpoint together on invalid data', () => {
  const cache = new Cache(':memory:');
  cache.commit('a', 'feed', [record('1')], { start: 1 });
  assert.throws(() => cache.commit('a', 'feed', [record('2'), { kind: 'post', text: 'Missing id' }], { start: 2 }));
  assert.equal(cache.get('a', '2'), null); assert.equal(cache.state('a', 'feed').cursor.start, 1);
  cache.close();
});

test('sync resumes at committed page after failure and does not lose a partially consumed page', async () => {
  const cache = new Cache(':memory:'); let fail = true; const requested = [];
  const fetchPage = async cursor => { const start = cursor?.start ?? 0; requested.push(start); if (start === 2 && fail) throw new Error('Disconnected'); return { records: [record(String(start)), record(String(start + 1))], next: start < 4 ? { start: start + 2 } : null, source: 'test' }; };
  await assert.rejects(sync(cache, 'a', 'feed', fetchPage, { limit: 4, maxPages: 3 }), /Disconnected/);
  assert.equal(cache.state('a', 'feed').cursor.start, 2); assert.equal(cache.list('a').length, 2);
  fail = false; const result = await sync(cache, 'a', 'feed', fetchPage, { limit: 3, maxPages: 3, resume: true });
  assert.equal(requested[2], 2); assert.equal(result.data.length, 3);
  // The full fetched page is cached even when the output limit cuts through it.
  assert.equal(cache.list('a').length, 6); assert.equal(cache.state('a', 'feed').cursor, null);
  cache.close();
});

test('repeated cursors fail as partial progress, without silently looping', async () => {
  const cache = new Cache(':memory:');
  await assert.rejects(sync(cache, 'a', 'x', async () => ({ records: [record('1')], next: { start: 0 } }), { limit: 20, maxPages: 3 }), e => e.code === 'PAGINATION_STALLED');
  assert.equal(cache.list('a').length, 1); cache.close();
});

test('a killed sync process can resume immediately from its last committed page', async () => {
  const { mkdtempSync, rmSync } = await import('node:fs'); const { tmpdir } = await import('node:os'); const { join } = await import('node:path'); const { spawn } = await import('node:child_process');
  const dir = mkdtempSync(join(tmpdir(), 'linkedin-killed-')), path = join(dir, 'cache.sqlite');
  const source = `import {Cache} from ${JSON.stringify(new URL('../linkedin',import.meta.url).href)};const c=new Cache(${JSON.stringify(path)});c.startRun('a','feed');c.commit('a','feed',[{id:'1',kind:'post',text:'Saved'}],{start:1});console.log('ready');setInterval(()=>{},1000);`;
  const child = spawn(process.execPath, ['--input-type=module', '-e', source], { stdio: ['ignore', 'pipe', 'inherit'] });
  await new Promise((resolve,reject) => { child.stdout.once('data',resolve);child.once('error',reject); });
  child.kill('SIGKILL'); await new Promise(resolve => child.once('close',resolve));
  const cache = new Cache(path);
  try {
    const result = await sync(cache,'a','feed',async cursor=>({records:[record(String(cursor.start+1))],next:null}),{resume:true,limit:2});
    assert.equal(result.data[0].id,'2'); assert.equal(cache.list('a').length,2);
    assert.ok(cache.status('a').runs.some(run=>run.status==='interrupted'));
  } finally {cache.close();rmSync(dir,{recursive:true});}
});

test('legacy archive keeps typed details plus a lossless backup row', () => {
  const records = archiveRecords({ type: 'post', id: 'urn:li:activity:123', content: 'A useful post', authorName: 'Example', authorProfile: 'https://www.linkedin.com/in/example/', postedAt: '2026-01-01T00:00:00Z', postedAtConfidence: 'relative', rawText: 'NO_RAW', media: [{ kind: 'image', url: 'https://media.example/image' }], analytics: { saveCount: 4 }, scrapedAt: '2026-02-01T00:00:00Z' });
  assert.equal(records[0].text, 'A useful post'); assert.equal(records[0].analytics.saveCount, 4);
  assert.equal(records[0].publishedAtConfidence, 'relative'); assert.equal(records[0].backupRow.rawText,'NO_RAW');assert.notEqual(records[0].text,'NO_RAW');
  const comment = archiveRecords({ type: 'comment', id: 'c2', parentId: 'urn:li:activity:123', parentCommentId: 'c1', commenterName: 'Reader', content: 'A reply' })[0];
  assert.equal(comment.parentId, 'c1'); assert.equal(comment.postId, 'urn:li:activity:123');
});

test('JSONL imports are idempotent, preserve edits and report line-numbered malformed input', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'linkedin-test-')); const path = join(dir, 'archive.jsonl'); const cache = new Cache(':memory:');
  try {
    writeFileSync(path, JSON.stringify({ type: 'post', id: 'p', content: 'hello', scrapedAt: '2026-01-01T00:00:00Z' }) + '\n');
    await importArchive(cache, 'a', path); await importArchive(cache, 'a', path);
    assert.equal(cache.list('a').length, 1);
    writeFileSync(path, '{malformed}\n'); await assert.rejects(importArchive(cache, 'a', path), /line 1/);
  } finally { cache.close(); rmSync(dir, { recursive: true }); }
});

test('history import uses read-only SQLite, exact hosts, title+URL deduplication and stays offline', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'linkedin-history-')); const path = join(dir, 'history.db'); const db = new DatabaseSync(path);
  db.exec('CREATE TABLE activity(url,title,timestamp,activity_source)');
  const put = db.prepare('INSERT INTO activity VALUES(?,?,?,?)');
  put.run('https://www.linkedin.com/in/example/?trk=x', 'Example person', '2026-01-01', 'history');
  put.run('https://www.linkedin.com/in/example/?trk=y', 'Example person', '2026-01-02', 'history');
  put.run('https://linkedin.com.evil/in/bad/', 'Wrong host', '2026-01-01', 'history'); db.close();
  const cache = new Cache(':memory:');
  try { await importHistory(cache, 'a', path); assert.equal(cache.search('a', 'Example').length, 1); assert.equal(cache.search('a', 'Wrong').length, 0); }
  finally { cache.close(); rmSync(dir, { recursive: true }); }
});

test('analytics distinguishes discovery value-before-label from engagement label-before-value', () => {
  const text = 'Discovery\n1,200\nImpressions\n300\nMembers reached\nIn-network (followers and connections)\n25%\nOut-of-network\n75%\nProfile activity\n4\nProfile viewers from this post\n2\nFollowers gained from this post\nEngagement\n40\nSocial engagements\nReactions\n30\nComments\n5\nReposts\n2\nSaves\n3\nSends on LinkedIn\n0';
  const result = parseAnalytics({ text, url: 'https://www.linkedin.com/analytics/post-summary/urn:li:activity:123/' }, 'urn:li:activity:123');
  assert.equal(result.analytics.impressionCount, 1200); assert.equal(result.analytics.reactionCount, 30);
  assert.equal(result.analytics.commentCount, 5); assert.equal(result.analytics.sendCount, 0);
  assert.equal(result.analytics.inNetworkPercent, 25); assert.equal(result.analytics.profileViewers, 4);
});

test('analytics keeps absent and withheld metrics unknown, and rejects a non-analytics page', () => {
  const result = parseAnalytics({ text: 'Discovery\n100\nImpressions\nEngagement\nSaves\n—', url: 'https://www.linkedin.com/analytics/' }, 'p');
  assert.equal(result.analytics.saveCount, null); assert.equal(result.analytics.membersReached, null);
  assert.equal(parseAnalytics({ text: 'Sign in to LinkedIn', url: '' }, 'p'), null);
});

test('native backup updates the durable archive and cache without Python', async()=>{
  const dir=await mkdtemp(join(tmpdir(),'linkedin-native-')),file=join(dir,'posts.jsonl');
  const original={type:'post',id:'p',url:'https://www.linkedin.com/feed/update/urn:li:activity:123/',authorName:'Example',authorProfile:'https://www.linkedin.com/in/example/',content:'Complete original text',scrapedAt:'2026-01-01T00:00:00Z',rawText:'Historical raw text',postedAt:'2025-12-01T00:00:00Z',futureField:{keep:true},analytics:{saveCount:2}};
  await writeFile(file,JSON.stringify(original)+'\n');const cache=new Cache(':memory:');
  const client={async whoami(){return{username:'example'};},async backupAnalytics(row){return{type:'post',id:row.id,analytics:{saveCount:0},repostCount:0,scrapedAt:'2026-02-01T00:00:00Z'};}};
  try{const result=await backup(client,cache,'a','example',{file,analytics:true,limit:1});const rows=await readBackupArchive(file);
    assert.equal(result.summary.posts,1);assert.equal(rows[0].analytics.saveCount,0);assert.equal(rows[0].content,original.content);assert.deepEqual(rows[0].futureField,{keep:true});assert.equal(cache.get('a','p').analytics.saveCount,0);assert.equal(toBackupRow(cache.get('a','p')).rawText,original.rawText);
  }finally{cache.close();await rm(dir,{recursive:true});}
});

const self = { id: 'account', username: 'example', kind: 'profile', name: 'Example' };
function fixture() {
  const dir = mkdtempSync(join(tmpdir(), 'linkedin-cli-test-')); const path = join(dir, 'cache.sqlite'); let calls = 0;
  const factory = () => ({ async open() { calls++; }, async close() {}, async whoami() { return self; }, async profile() { return { ...self, text: 'Builds useful tools' }; }, async search() { return { records: [{ id: 'p', kind: 'profile', name: 'Reader', headline: 'Engineer' }], next: null, source: 'test' }; } });
  return { dir, path, factory, calls: () => calls, clean() { rmSync(dir, { recursive: true }); } };
}

test('every online read auto-caches; offline and fresh-cache profile reads never open a browser', async () => {
  const f = fixture();
  try {
    await run(['profile', 'example', '--db', f.path], { clientFactory: f.factory, log() {} });
    const offline = await run(['profile', 'example', '--offline', '--db', f.path, '--cdp', 'http://localhost:1'], { clientFactory() { throw Error('Browser must not be touched'); } });
    assert.equal(offline.result.data.text, 'Builds useful tools'); assert.equal(offline.result.meta.offline, true);
    await run(['profile', 'example', '--db', f.path], { clientFactory() { throw Error('Browser must not be touched'); } });
    assert.equal(f.calls(), 1);
  } finally { f.clean(); }
});

test('schema/params, aliases and strict invalid-input errors work without credentials', async () => {
  const described = await run(['--describe'], { clientFactory() { throw Error('no network'); } });
  assert.ok(described.result.commands.profile);
  const parsed = parse(['--params', JSON.stringify({ args: ['search', 'people', 'Example'], limit: '3', offline: true })]);
  assert.equal(parsed.operation, 'people'); assert.equal(parsed.limit, 3);
  assert.equal(parse(['cache', 'search', 'Example']).operation, 'find');
  for (const argv of [['people', 'x', '--limit', '-1'], ['search', 'people', 'x', '--unknown'], ['--params', '{"bogus":true}'], ['profile', 'x', '--sections', 'bad'], ['sync', 'feed', '--resume'], ['profile', 'x', '--offline', '--refresh']]) assert.throws(() => parse(argv));
});

test('field masks are nested, and NDJSON emits records followed by a typed summary', () => {
  const result = { ok: true, data: [{ id: 'p', text: 'Long text', author: { name: 'Example', url: 'private-url' } }], meta: { source: 'test' } };
  const rows = render(result, 'ndjson', 'id,author.name').trim().split('\n').map(JSON.parse);
  assert.equal(rows[0].data.author.name, 'Example'); assert.equal(rows[0].data.text, undefined); assert.equal(rows[0].data.author.url, undefined);
  assert.equal(rows[1].type, 'summary'); assert.equal(rows[1].data, undefined);
});

test('an explicit account mismatch does not write records under the requested account', async () => {
  const f = fixture();
  try {
    await assert.rejects(run(['profile', 'example', '--account', 'other', '--db', f.path], { clientFactory: f.factory, log() {} }), error => error.code === 'ACCOUNT_MISMATCH');
    const cache = new Cache(f.path); assert.equal(cache.list('other').length, 0); cache.close();
  } finally { f.clean(); }
});

test('offline comment threads retain reply parents from imported archive records', async () => {
  const f = fixture();
  try {
    const cache = new Cache(f.path); cache.useAccount('a', 'example');
    cache.commit('a', 'import', [{ id: 'c1', kind: 'comment', postId: 'urn:li:activity:123', parentId: 'urn:li:activity:123', text: 'Parent' }, { id: 'c2', kind: 'comment', postId: 'urn:li:activity:123', parentId: 'c1', text: 'Reply' }], null); cache.close();
    const result = await run(['comments', 'urn:li:activity:123', '--db', f.path], { clientFactory() { throw Error('No network'); } });
    assert.equal(result.result.data.length, 2); assert.equal(result.result.data.find(r => r.id === 'c2').parentId, 'c1');
  } finally { f.clean(); }
});

test('empty help, numeric JSON params, field validation and symlink entry point are usable', async () => {
  const { spawnSync } = await import('node:child_process');
  assert.equal(parse([]).values.help, true);
  assert.equal(parse(['--params','{"args":["people","Example"],"limit":3}']).limit, 3);
  assert.throws(()=>parse(['people','Example','--fields','constructor.polluted']));
  const child=spawnSync(process.execPath,[SCRIPT,'--describe'],{encoding:'utf8'});
  assert.equal(child.status,0);assert.equal(JSON.parse(child.stdout).name,'linkedin');
});

test('an archived post and its analytics can be read offline without an exact query checkpoint', async () => {
  const f=fixture();
  try {
    const cache=new Cache(f.path);cache.useAccount('a','example');cache.commit('a','import',[{id:'urn:li:activity:123',kind:'post',text:'Archived',analytics:{saveCount:5}}],null);cache.close();
    const noNetwork={clientFactory(){throw Error('No network');}};
    const post=await run(['post','1234567890','--offline','--db',f.path],noNetwork).catch(e=>e);assert.equal(post.code,'CACHE_MISS');
    const analytics=await run(['analytics','urn:li:activity:123','--offline','--db',f.path],noNetwork);assert.equal(analytics.result.data.analytics.saveCount,5);
  } finally {f.clean();}
});

test('Markdown is the default, md is an alias, and analytics/status metadata remain visible', () => {
  assert.equal(parse(['profile','example']).format,'markdown');
  assert.equal(parse(['profile','example','--format','md']).format,'markdown');
  const result={ok:true,data:{kind:'analytics',analytics:{reactionCount:4,commentCount:2,repostCount:1,impressionCount:123,saveCount:0}},warnings:['Visible only']};
  const output=render(result);assert.match(output,/Reactions/);assert.match(output,/123/);assert.match(output,/Saves/);assert.match(output,/Visible only/);
  assert.match(render({ok:true,data:{counts:[{kind:'post',records:20}]}}),/20/);
});

test('documented search filters are real facets, strict and isolated in cache keys', async () => {
  const parsed=parse(['search','people','engineer','--location','102454443','--organization','123','--degree','1,2']);
  assert.deepEqual(searchFacets(parsed.values),[{key:'geoUrn',value:['102454443']},{key:'currentCompany',value:['123']},{key:'network',value:['F','S']}]);
  assert.throws(()=>parse(['profile','example','--degree','1']));
  assert.throws(()=>searchFacets({degree:'4'}));
  assert.deepEqual(searchFacets({location:'Chennai'}),[{key:'geoUrn',value:['Chennai']}]);
  assert.throws(()=>searchFacets({location:'urn:li:bad:123'}));
  const c=new Client();let captured;c.gql=async(id,args)=>{captured=args;return {data:{data:{searchDashClustersByAll:{paging:{total:0},elements:[]}}},included:[]};};
  await c.search('people','engineer',null,5,searchFacets(parsed.values));
  assert.ok(captured.query.queryParameters.some(f=>f.key==='network'&&f.value[0]==='F'));
  const f=fixture();
  try{await run(['people','Example','--organization','123','--db',f.path],{clientFactory:f.factory,log(){}});
    await assert.rejects(run(['people','Example','--organization','456','--offline','--db',f.path],{clientFactory(){throw Error('No network');}}),e=>e.code==='CACHE_MISS');
  }finally{f.clean();}
});

test('analytics selection supports relative dates and refreshes own metrics, including zeros, into post/cache records', async () => {
  assert.equal(sinceDate('7d',new Date('2026-11-09T00:00:00Z')),'2026-11-02T00:00:00.000Z');
  assert.throws(()=>sinceDate('nonsense'));
  const cache=new Cache(':memory:'); const owner={id:'a',username:'example',name:'Example'};let reads=0;
  const client={async activity(){return {records:[{id:'urn:li:activity:123',kind:'post',author:{url:'https://www.linkedin.com/in/example/'},text:'Own post'}],next:null};},async analytics(id){reads++;return {id:'analytics:'+id,kind:'analytics',postId:id,analytics:{reactionCount:0,commentCount:2,repostCount:1,impressionCount:100},source:'test'};}};
  try{const result=await syncAnalytics(cache,'a','analytics-test',client,owner,{limit:1,maxPages:1,pageSize:1,log(){}});
    assert.equal(reads,1);assert.equal(result.data.length,1);assert.equal(cache.get('a','urn:li:activity:123').reactionCount,0);assert.equal(cache.get('a','analytics:urn:li:activity:123').analytics.impressionCount,100);
  }finally{cache.close();}
});

test('analytics batches preserve completed post updates when a later post fails and resume the unfinished page', async () => {
  const cache=new Cache(':memory:');const owner={id:'a',username:'example'};let fail=true;
  const client={async activity(){return {records:['1','2'].map(id=>({id:'urn:li:activity:'+id,kind:'post',author:{url:'https://www.linkedin.com/in/example/'}})),next:null};},async analytics(id){if(id.endsWith(':2')&&fail)throw Error('Disconnected');return {id:'analytics:'+id,kind:'analytics',postId:id,analytics:{impressionCount:100},source:'test'};}};
  try{await assert.rejects(syncAnalytics(cache,'a','batch',client,owner,{limit:2,maxPages:1,pageSize:2,log(){}}),/Disconnected/);
    assert.equal(cache.get('a','analytics:urn:li:activity:1').analytics.impressionCount,100);assert.ok(cache.state('a','batch').cursor);
    fail=false;const result=await syncAnalytics(cache,'a','batch',client,owner,{limit:2,maxPages:1,pageSize:2,resume:true,log(){}});assert.equal(result.data.length,2);
  }finally{cache.close();}
});

test('single-post analytics rejects another author before opening any analytics page', async () => {
  const c=new Client();c.whoami=async()=>({id:'a',username:'example'});c.post=async()=>({id:'urn:li:activity:123',author:{url:'https://www.linkedin.com/in/someone-else/'}});c.background=async()=>{throw Error('Must not navigate');};
  await assert.rejects(c.analytics('urn:li:activity:123'),e=>e.code==='FORBIDDEN');
});

test('the standalone module is importable from stdin without running the CLI', async () => {
  const {spawnSync}=await import('node:child_process');
  const child=spawnSync(process.execPath,['--input-type=module','-'],{encoding:'utf8',input:`await import(${JSON.stringify(new URL('../linkedin',import.meta.url).href)});console.log('imported');`});
  assert.equal(child.status,0,child.stderr);assert.equal(child.stdout.trim(),'imported');
});

test('a competing analytics batch cannot reset the active collection checkpoint', async () => {
  const cache=new Cache(':memory:');cache.commit('a','batch',[],{start:50});const lease=cache.startRun('a','batch');
  try{await assert.rejects(syncAnalytics(cache,'a','batch',{}, {username:'example'},{limit:1,maxPages:1}),e=>e.code==='SYNC_BUSY');assert.equal(cache.state('a','batch').cursor.start,50);}
  finally{cache.finishRun(lease,'ok','test');cache.close();}
});

const mdContext=(operation,args=[],values={})=>({operation,args,values});
const mdPost={id:'urn:li:activity:123',kind:'post',url:'https://www.linkedin.com/feed/update/urn:li:activity:123/',author:{name:'Ada Rao',url:'https://www.linkedin.com/in/ada/',headline:'Researcher'},text:'A useful first paragraph.\n\nA second paragraph with **emphasis**.',publishedAt:'2026-11-09T10:30:00Z',reactionCount:12,commentCount:0,repostCount:2,impressionCount:1234};

test('Markdown profiles and search lists have one document title, working links and readable sections',()=>{
  const profile={kind:'profile',name:'Ada Rao',headline:'Researcher',location:'Singapore',url:'https://www.linkedin.com/in/ada/',text:'Builds useful tools.',sections:{experience:'Experience\nEngineer\nExample Labs',education:'Example University'}};
  const one=render({ok:true,data:profile},'md',undefined,mdContext('profile',['ada']));
  assert.match(one,/^# Ada Rao\n/);assert.match(one,/## About/);assert.match(one,/## Experience/);assert.match(one,/Singapore · https:\/\/www.linkedin.com\/in\/ada\//);assert.doesNotMatch(one,/```json/);
  const list=render({ok:true,data:[profile,{...profile,name:'Ben | Shah',url:'https://www.linkedin.com/in/ben/'}]},'md',undefined,mdContext('people',['researchers']));
  assert.equal((list.match(/^# /gm)||[]).length,1);assert.match(list,/researchers/);assert.match(list,/Ben \\?\| Shah/);assert.match(list,/2 (?:people|results)/i);
});

test('Markdown posts keep full content, real media links and human engagement counts without schema field names',()=>{
  const output=render({ok:true,data:{...mdPost,media:[{kind:'image',url:'https://example.com/chart.png',alt:'A [useful] chart'}],links:['https://example.com/article']}},'markdown',undefined,mdContext('post',[mdPost.id]));
  assert.match(output,/A second paragraph with \*\*emphasis\*\*/);assert.match(output,/1,234/);assert.match(output,/0 comments/);assert.match(output,/chart\.png/);assert.match(output,/article/);assert.match(output,/2026/);assert.doesNotMatch(output,/reactionCount|commentCount|urn:li:activity:123(?=[\s`])/);
});

test('Markdown analytics presents labeled metrics, unknowns, percentages, zero and timestamp without dumping UI text',()=>{
  const data={kind:'analytics',postId:mdPost.id,url:'https://www.linkedin.com/analytics/post-summary/'+mdPost.id+'/',observedAt:'2026-11-09T12:00:00Z',text:'RAW_UI_NAVIGATION_NOISE',analytics:{impressionCount:1234,reactionCount:12,likes:12,commentCount:0,repostCount:2,saveCount:null,inNetworkPercent:25,demographics:{Location:[{label:'Singapore',percentage:60}]}}};
  const one=render({ok:true,data},'md',undefined,mdContext('analytics',[mdPost.id]));
  for(const value of ['Impressions','1,234','Reactions','Comments','Saves','25%','Singapore','2026'])assert.ok(one.includes(value),value);
  assert.match(one,/- Comments: 0/);assert.match(one,/- Saves: —/);assert.doesNotMatch(one,/RAW_UI|impressionCount|```json/);
  const batch=render({ok:true,data:[data,{...data,postId:'urn:li:activity:456'}]},'md',undefined,mdContext('analytics',['me']));
  assert.equal((batch.match(/^# /gm)||[]).length,1);assert.match(batch,/2 posts/);assert.match(batch,/\|.*Impressions.*Reactions.*Comments.*Reposts/);
});

test('Markdown comments form a readable thread, and activity distinguishes the commenter from the post author',()=>{
  const root={id:'c1',kind:'comment',author:{name:'Ada Rao'},text:'Parent comment',postId:mdPost.id,parentId:mdPost.id};
  const reply={...root,id:'c2',author:{name:'Ben Shah'},text:'A reply',parentId:'c1'};
  const thread=render({ok:true,data:[reply,root]},'md',undefined,mdContext('comments',[mdPost.id]));
  assert.ok(thread.indexOf('Parent comment')<thread.indexOf('A reply'));assert.match(thread,/Reply to/);assert.match(thread,/\]\(#comment-/);assert.equal((thread.match(/A reply/g)||[]).length,1);
  const activity=render({ok:true,data:[{kind:'activity',activityKind:'comments',actor:{name:'Ben Shah'},post:mdPost,text:mdPost.text}]},'md',undefined,mdContext('activity',['ben'],{kind:'comments'}));
  assert.match(activity,/Ben Shah/);assert.match(activity,/Ada Rao/);assert.match(activity,/post by \[?Ada Rao/i);assert.doesNotMatch(activity,/Ben Shah\n\nA useful/);
});

test('Markdown status, imports, backup, previews, empty results and pagination are useful prose/tables',()=>{
  const cases=[
    ['cache status',{account:'account',counts:[{kind:'post',records:1234}],collections:[{key:'{"operation":"people","args":["engineer"]}',updated_at:'2026-11-09T12:00:00Z',resumable:1}],runs:[{status:'ok',collection:'feed',started_at:'2026-11-09T12:00:00Z',pages:2,records:10,reason:'item_limit'}]},['LinkedIn cache','1,234','engineer']],
    ['import archive',{imported:3403,changed:5,collection:'import:archive:/private/file.jsonl'},['3,403','5','import']],
    ['backup',{imported:10,changed:2,originalArchiveModified:false,summary:{posts:2,status:'ok'}},['10','2','preserved']],
  ];
  for(const[operation,data,expected]of cases){const output=render({ok:true,data},'md',undefined,mdContext(operation));for(const value of expected)assert.ok(output.toLowerCase().includes(value.toLowerCase()),`${operation}: ${value}`);assert.doesNotMatch(output,/```json|updated_at|item_limit|\/private\/file/);}
  const preview=render({ok:true,data:{operation:'profile',args:['ada'],network:true,cacheWrites:true,limit:20,maxPages:2},meta:{dry_run:true}},'md',undefined,mdContext('profile',['ada']));assert.match(preview,/Preview/);assert.match(preview,/No changes/);
  const empty=render({ok:true,data:[],meta:{source:'cache'}},'md',undefined,mdContext('find',['nothing']));assert.match(empty,/No .*matches/i);assert.match(empty,/nothing/);
  const paged=render({ok:true,data:[mdPost],page:{next:{resumable:true},fetched:5,returned:1},coverage:{complete:false,reason:'item_limit'},meta:{source:'cache',stale:true}},'md',undefined,mdContext('activity',['me']));assert.match(paged,/--resume/);assert.match(paged,/out of date|stale/i);assert.doesNotMatch(paged,/item_limit|Source: cache/);
});

test('Markdown supports invitations, history, reposts, safe table text, and field masks without changing JSON/JSONL',()=>{
  const cases=[['invitations',{kind:'invitation',name:'Ada',headline:'Builder',text:'Would like to connect.',sentAt:1794225600000,url:'https://www.linkedin.com/in/ada/'}],['find',{kind:'history',name:'Useful article',url:'https://example.com/article',visitedAt:'2026-11-09T12:00:00Z'}],['reposts',{name:'Ada',profile:'https://www.linkedin.com/in/ada/',content:'Thoughtful repost',postedText:'2d',reactionCount:0}]];
  for(const[operation,record]of cases){const output=render({ok:true,data:[record]},'md',undefined,mdContext(operation,['topic']));assert.match(output,/# /);assert.ok(output.includes(record.text??record.content??record.name));assert.doesNotMatch(output,/```json/);}
  const hidden=render({ok:true,data:mdPost},'md','author.name',mdContext('post'));assert.match(hidden,/Ada Rao/);assert.doesNotMatch(hidden,/A useful first paragraph/);
  const original={ok:true,data:[mdPost],meta:{source:'cache'},warnings:['Visible only']};const before=JSON.stringify(original);
  render(original,'md',undefined,mdContext('post'));assert.equal(JSON.stringify(original),before);
  assert.deepEqual(JSON.parse(render(original,'json')),original);assert.equal(JSON.stringify(original),before);
  const rows=render(original,'ndjson').trim().split('\n').map(JSON.parse);assert.deepEqual(rows[0].data,mdPost);assert.equal(rows[1].type,'summary');
});

test('Markdown field selections keep IDs visible, explain missing fields and escape URLs inside tables',()=>{
  const data=[{id:'p1',kind:'profile',name:'A | [B]',url:'https://example.com/a|b',headline:'Builder'},{id:'p2',kind:'profile',name:'Other',url:'https://example.com/other'}];
  const ids=render({ok:true,data},'md','id',mdContext('people',['builders']));assert.match(ids,/p1/);assert.match(ids,/p2/);assert.doesNotMatch(ids,/Builder/);
  const absent=render({ok:true,data},'md','nonexistent',mdContext('people',['builders']));assert.match(absent,/selected fields/);assert.doesNotMatch(absent,/\|\s*\|/);
  const full=render({ok:true,data},'md',undefined,mdContext('people',['builders']));assert.match(full,/a%7Cb/);assert.doesNotMatch(full,/\(<https:\/\/example.com\/a\|b/);
});

test('Markdown content headings stay inside one document, fences survive, and unknown provenance is readable',()=>{
  const sample={...mdPost,text:'# A title\n\n## A section\n\n```js\n# inside code\n```\n\n<script>never run</script>'};
  const output=render({ok:true,data:sample,meta:{source:'future-adapter'}},'md',undefined,mdContext('post'));
  assert.match(output,/### A title/);assert.match(output,/```js\n# inside code\n```/);assert.match(output,/&lt;script>/);assert.doesNotMatch(output,/Data source: undefined/);
  const one=render({ok:true,data:[{kind:'profile',name:'Ada'}]},'md',undefined,mdContext('people',['builder']));assert.match(one,/1 person/);assert.doesNotMatch(one,/1 people/);
});

test('Markdown preserves month-only precision and closes an unfinished source code fence before document notes',()=>{
  const invitation=render({ok:true,data:[{kind:'invitation',name:'Ada',invitationMonth:'August 2026'}]},'md',undefined,mdContext('invitations'));
  assert.match(invitation,/August 2026/);assert.doesNotMatch(invitation,/UTC|31 Jul/);
  const post=render({ok:true,data:{...mdPost,text:'```js\nconst answer = 42;'},meta:{source:'cache'}},'md',undefined,mdContext('post'));
  assert.match(post,/const answer = 42;\n```/);assert.ok(post.indexOf('\n```\n')<post.indexOf('Read from your local cache'));
});

test('Markdown retains every explicitly selected field even alongside a name or normal profile fields',()=>{
  const data={id:'profile-123',kind:'profile',name:'Ada Rao',source:'voyager',industry:'Research',observedAt:'2026-11-09T12:00:00Z'};
  for(const value of [data,[data]]){const output=render({ok:true,data:value},'md','id,name,source,industry,observedAt',mdContext('profile',['ada']));for(const text of ['profile-123','Ada Rao','voyager','Research','2026'])assert.ok(output.includes(text),text);assert.doesNotMatch(output,/observedAt/);}
});

test('Markdown cache lookups use the saved record type for standalone document titles',()=>{
  for(const[data,title]of [[{kind:'company',name:'Example Labs',headline:'Research'},'Example Labs'],[{kind:'comment',id:'c',text:'A useful comment'},'Comment'],[{kind:'activity',actor:{name:'Ada'},post:mdPost,activityKind:'reactions'},'Member activity'],[{kind:'history',name:'Useful link',url:'https://example.com'},'Useful link']]){const output=render({ok:true,data},'md',undefined,mdContext('cache get',['saved-id']));assert.equal(output.split('\n')[0],'# '+title);}
});

test('terminal Markdown combines counts and dates in the title and puts raw row links last',()=>{
  const data={kind:'analytics',postId:mdPost.id,analytics:{profileViewers:8,followersGained:0}};
  const batch=render({ok:true,data:[data,data,data,data]},'md',undefined,mdContext('analytics',['me'],{since:'30d'}));
  assert.match(batch,/^# Post analytics \(30d, 4 posts\)\n/);
  assert.doesNotMatch(batch,/^From 30d$|^4 posts$/m);
  const people=render({ok:true,data:[{kind:'profile',name:'First Last',headline:'Engineer at Microsoft',location:'Bengaluru',url:'https://www.linkedin.com/in/abcd'}]},'md',undefined,mdContext('people',['engineer']));
  assert.match(people,/\| Name \| Headline \| Location \| Link \|/);
  assert.match(people,/\| First Last \| Engineer at Microsoft \| Bengaluru \| https:\/\/www.linkedin.com\/in\/abcd \|/);
  assert.doesNotMatch(people,/\[First Last\]/);
  const metrics=render({ok:true,data},'md',undefined,mdContext('analytics',[mdPost.id]));
  assert.match(metrics,/- Profile views: 8\n- Followers gained: 0/);
  assert.doesNotMatch(metrics,/\| Metric \| Value \|/);
});

test('terminal Markdown keeps explicitly selected URL fields at the end of table rows',()=>{
  const output=render({ok:true,data:[{url:'https://example.com/person',name:'First Last',id:'p1'}]},'md','url,name,id',mdContext('people',['engineer']));
  assert.match(output,/\| Name \| ID \| Link \|/);
  assert.match(output,/\| First Last \| p1 \| https:\/\/example.com\/person \|/);
});

test('standalone executable runs and imports without an extension or package metadata',async()=>{
  const {spawnSync}=await import('node:child_process');
  const directory=await mkdtemp(join(tmpdir(),'linkedin-executable-'));
  try{
    const executable=join(directory,'linkedin');await writeFile(executable,await readFile(SCRIPT),{mode:0o755});
    const child=spawnSync('linkedin',['--describe'],{cwd:directory,env:{...process.env,PATH:directory+':'+process.env.PATH},encoding:'utf8'});
    assert.equal(child.status,0,child.stderr);assert.ok(JSON.parse(child.stdout).commands.analytics);
    const imported=spawnSync(process.execPath,['--input-type=module','-'],{cwd:directory,encoding:'utf8',input:`const m=await import(${JSON.stringify(new URL('file://'+executable).href)});console.log(typeof m.render);`});
    assert.equal(imported.status,0,imported.stderr);assert.equal(imported.stdout.trim(),'function');
  }finally{await rm(directory,{recursive:true,force:true});}
});


test('backup import/export round trips unknown fields, replies, nulls and typed details',()=>{
 const rows=[{type:'post',id:'p',content:'Full post',authorName:'Example',authorProfile:'https://www.linkedin.com/in/example/',scrapedAt:'2026-01-01T00:00:00Z',postedAt:'2025-12-01T00:00:00Z',postedAtConfidence:'id',rawText:'Raw body',reactionCount:0,impressionCount:null,analytics:{saveCount:null},futureField:{nested:[1,2]}},{type:'comment',id:'c',parentId:'p',parentCommentId:'parent',content:'Reply',commenterName:'Other',reactedByAuthor:false,commentedAt:'2025-12-01T00:00:00Z',commentedAtConfidence:'id',scrapedAt:'2026-01-01T00:00:00Z',reactionText:'0',rawText:'Full comment',socialText:''}];
 const cache=new Cache(':memory:');try{cache.commit('a','import',rows.flatMap(archiveRecords),null);const exported=exportBackupRows(cache,'a');assert.equal(exported.length,2);for(const row of rows)assert.deepEqual(exported.find(r=>r.id===row.id),row);cache.commit('b','import',rows.flatMap(archiveRecords),null);assert.equal(exportBackupRows(cache,'a').length,2);cache.commit('a','feed',[{id:'unrelated',kind:'post',text:'Other person’s feed post'}],null);assert.equal(exportBackupRows(cache,'a').length,2);}finally{cache.close();}
});

test('backup merge keeps rich fields, accepts zero/false, and preserves prior partial repost details',()=>{
 const old={type:'post',id:'p',content:'Long useful content',commentCount:12,edited:true,postedAt:'2025-01-01',postedAtConfidence:'id',reposts:[{id:'r1',content:'Full repost'}],future:'retained'};
 const row=mergeBackupRow(old,{type:'post',id:'p',content:'',commentCount:0,edited:false,postedAt:'2026-01-01',postedAtConfidence:'relative',reposts:[{id:'r2'}],repostScrapeStats:{complete:false}});
 assert.equal(row.content,old.content);assert.equal(row.commentCount,0);assert.equal(row.edited,false);assert.equal(row.postedAt,old.postedAt);assert.equal(row.future,'retained');assert.equal(row.reposts.length,2);
 assert.deepEqual(mergeBackupRow(row,{reposts:[],repostScrapeStats:{complete:true}}).reposts,[]);
});

test('archive writes are atomic/idempotent, keep historical rows, reject corruption and serialize writers',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'linkedin-archive-')),file=join(dir,'posts.jsonl');
 try{await writeBackupArchive(file,[{type:'post',id:'old',content:'Historical'}]);await writeBackupArchive(file,[{type:'post',id:'new',content:'New'}]);const before=await readFile(file,'utf8');assert.equal((await readBackupArchive(file)).length,2);assert.equal((await writeBackupArchive(file,[{type:'post',id:'new',content:'New'}])).changed,0);assert.equal(await readFile(file,'utf8'),before);
 const release=await lockBackupArchive(file);try{await assert.rejects(writeBackupArchive(file,[]),e=>e.code==='ARCHIVE_BUSY');}finally{await release();}
 await writeFile(file+'.lock',JSON.stringify({pid:2147483647,owner:'dead'}));await writeBackupArchive(file,[{type:'post',id:'third'}]);assert.equal((await readBackupArchive(file)).length,3);
 await writeFile(file,'{invalid');await assert.rejects(writeBackupArchive(file,[{type:'post',id:'fourth'}]),e=>e.code==='INVALID_ARCHIVE');assert.equal(await readFile(file,'utf8'),'{invalid');
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('native backup saves each completed post before interruption and a rerun retains history',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'linkedin-backup-partial-')),file=join(dir,'posts.jsonl'),cache=new Cache(':memory:');let fail=true;
 const client={async*backupPosts(){yield[{type:'post',id:'p1',content:'Completed',scrapedAt:'2026-01-01T00:00:00Z'}];if(fail)throw Error('Disconnected');yield[{type:'post',id:'p2',content:'Next',scrapedAt:'2026-01-01T00:00:00Z'}];}};
 try{await assert.rejects(backup(client,cache,'a','example',{file}),e=>e.partial.posts===1);assert.equal((await readBackupArchive(file)).length,1);assert.equal(cache.get('a','p1').text,'Completed');fail=false;await backup(client,cache,'a','example',{file});assert.equal((await readBackupArchive(file)).length,2);}finally{cache.close();await rm(dir,{recursive:true});}
});

test('corrupt native backup input fails before any DOM work and leaves the source intact',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'linkedin-backup-corrupt-')),file=join(dir,'posts.jsonl'),cache=new Cache(':memory:');await writeFile(file,'broken');
 try{await assert.rejects(backup({backupPosts(){throw Error('Must not open DOM');}},cache,'a','example',{file}),e=>e.code==='INVALID_ARCHIVE');assert.equal(await readFile(file,'utf8'),'broken');}finally{cache.close();await rm(dir,{recursive:true});}
});

test('backup CLI validates archive options and supports bounded unlimited backup and raw JSONL export',()=>{
 assert.equal(parse(['backup','me','--limit','0','--analytics','--since','7d','--until','1d']).limit,0);
 assert.equal(parse(['export','--schema','backup']).archiveExport,true);assert.equal(parse(['export','--schema','backup']).limit,0);
 for(const argv of [['people','engineer','--limit','0'],['backup','me','--since','7d'],['export','--schema','backup','--fields','id'],['profile','me','--archive','x'],['backup','me','--archive','a','--file','b'],['export','--schema','other']])assert.throws(()=>parse(argv));
});

test('compatible CLI export emits plain archive JSONL, without record/summary wrappers',async()=>{
 const {spawnSync}=await import('node:child_process');const dir=await mkdtemp(join(tmpdir(),'linkedin-export-')),path=join(dir,'cache.sqlite'),cache=new Cache(path);cache.useAccount('a','example');cache.commit('a','archive',archiveRecords({type:'post',id:'p',content:'Full text',scrapedAt:'2026-01-01T00:00:00Z'}),null);cache.close();
 try{const result=spawnSync(process.execPath,[SCRIPT,'export','--schema','backup','--db',path],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);const rows=result.stdout.trim().split('\n').map(JSON.parse);assert.equal(rows.length,1);assert.equal(rows[0].type,'post');assert.equal(rows[0].content,'Full text');assert.equal(rows[0].data,undefined);}finally{await rm(dir,{recursive:true});}
});

test('backup analytics selection excludes reposts/other authors and uses stable activity dates',()=>{
 const post={type:'post',id:'urn:li:activity:7470074745900802048',authorProfile:'https://www.linkedin.com/in/example/',postedAt:'2000-01-01'};
 assert.equal(selectBackupPosts([post,{...post,repostedBy:'Other'},{...post,authorProfile:'https://www.linkedin.com/in/other/'}],'example',{since:'2026-06-09',until:'2026-06-10'}).length,1);
 assert.equal(backupTimeFields({...post,postedText:'2d'},'2026-06-10T00:00:00Z').postedAtConfidence,'id');assert.equal(backupTimeFields({type:'comment',id:'c',commentedText:'2h'},'2026-06-10T00:00:00Z').commentedAt,'2026-06-09T22:00:00.000Z');
});

test('detailed analytics keeps video, viewers, all demographic rows and delayed zero metrics',()=>{
 const text='Discovery\n100\nImpressions\nVideo performance\n25\nVideo views\nWatch time\n1h\nAverage watch time\n15s\nEngagement\nReactions\n0\nComments\n0\nReposts\n0\nWho’s viewed your profile since this post\nA researcher\nView\nTry Premium\nAd copy\nTop demographics\nAll\nJob title\nLocation\nSeniority\nCompany\nIndustry\nCompany size\nSingapore\n60%\nAnalytics & tools';
 const record=parseDetailedBackupAnalytics({text,url:'https://www.linkedin.com/analytics/post-summary/urn:li:activity:123/'},'urn:li:activity:123');assert.equal(record.analytics.reactionCount,0);assert.equal(record.analytics.videoPerformance.views,25);assert.deepEqual(record.analytics.profileViewerSummary,['A researcher']);assert.equal(parseBackupDemographics(text,'Location')[0].percent,60);
 assert.equal(parseDetailedBackupAnalytics({text:text.replace('Reactions\n0','Reactions\nComments'),url:'https://www.linkedin.com/analytics/'},'p'),null);
});

test('native backup restores explicitly observed flat sibling replies without guessing unrelated comments',()=>{
 const rows=[{type:'comment',id:'parent',replyCount:2},{type:'comment',id:'older'},{type:'comment',id:'newer'},{type:'comment',id:'unrelated'}];applyBackupReplyParents(rows,{newer:'parent'});assert.equal(rows[1].parentCommentId,'parent');assert.equal(rows[2].parentCommentId,'parent');assert.equal(rows[3].parentCommentId,undefined);
});

test('keyed native DOM locators survive React card replacement and sibling reordering',async()=>{
 const {runInNewContext}=await import('node:vm');const {BackupNode}=await import('../linkedin');
 const node=(key,text)=>({getAttribute(name){return name==='componentkey'?key:null;},text});let nodes=[node('post-a','Old'),node('post-b','Other')];
 const document={querySelectorAll(){return nodes;}};const page={async call(method,params){assert.equal(method,'Runtime.evaluate');return{result:{value:runInNewContext(params.expression,{document})}};}};
 const root=new BackupNode(page);const pinned=(await root.all('cards'))[0];nodes=[node('post-b','Other'),node('post-a','Hydrated')];assert.equal(await pinned.value(el=>el.text),'Hydrated');nodes=[node('post-b','Other')];assert.equal(await pinned.value(el=>el.text),null);
});


test('dry-run compatible export never overwrites an existing archive and backup reports cannot replace data',async()=>{
 const {spawnSync}=await import('node:child_process');const dir=await mkdtemp(join(tmpdir(),'linkedin-dry-export-')),file=join(dir,'archive.jsonl');await writeFile(file,'original archive bytes');
 try{const child=spawnSync(process.execPath,[SCRIPT,'export','--schema','backup','--dry-run','--output',file],{encoding:'utf8'});assert.equal(child.status,0,child.stderr);assert.equal(await readFile(file,'utf8'),'original archive bytes');assert.match(child.stdout,/Preview/);assert.throws(()=>parse(['backup','me','--archive',file,'--output',file]),e=>e.code==='INVALID_INPUT');}finally{await rm(dir,{recursive:true});}
});

test('comment opening is verified and retried when SSR controls precede their event handlers',async()=>{
 const {loadBackupComments}=await import('../linkedin');let opened=false,clicks=0;
 const button={async click(){clicks++;if(clicks>=2)opened=true;return 1;}};
 const post={settleMs:0,async value(fn){return fn({querySelector(){return {innerText:'1'};},querySelectorAll(){return [];}});},async all(selector){
  if(selector.startsWith('[componentkey^="commentsSectionContainer"]'))return opened?[{}]:[];
  if(selector.startsWith('article.comments-comment-entity'))return opened?[{}]:[];
  if(selector.startsWith('button[aria-label="Comment"]'))return [button];
  return [];
 }};
 const stats=await loadBackupComments(post,{maxRounds:8});assert.equal(clicks,2);assert.equal(stats.commentsLoaded,1);assert.equal(stats.complete,true);
});

// Backup regressions use a fresh headless profile, never the authenticated CDP browser.
let backupTestBrowser;
async function backupBrowser(){
  if(backupTestBrowser)return backupTestBrowser;
  backupTestBrowser=(async()=>{
    const {readdir,access}=await import('node:fs/promises'),{homedir}=await import('node:os'),{spawn}=await import('node:child_process');
    const root=process.env.PLAYWRIGHT_BROWSERS_PATH||join(homedir(),'.cache/ms-playwright');
    const directories=(await readdir(root)).filter(s=>/^chromium(?:_headless_shell)?-/.test(s)).sort((a,b)=>b.localeCompare(a,undefined,{numeric:true}));let executable;
    for(const directory of directories){for(const file of ['chrome-headless-shell-linux64/chrome-headless-shell','chrome-headless-shell-win64/chrome-headless-shell.exe','chrome-headless-shell-mac-arm64/chrome-headless-shell','chrome-headless-shell-mac-x64/chrome-headless-shell','chrome-linux64/chrome','chrome-linux/chrome','chrome-win64/chrome.exe']){const path=join(root,directory,file);try{await access(path);executable=path;break;}catch{}}if(executable)break;}
    assert.ok(executable,'Chromium is required for backup DOM regressions; run just playwright-install');
    const directory=await mkdtemp(join(tmpdir(),'linkedin-dom-browser-'));const child=spawn(executable,['--headless','--no-sandbox','--disable-gpu','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows','--remote-debugging-port=0','--remote-debugging-address=127.0.0.1','--user-data-dir='+directory],{stdio:['ignore','ignore','pipe']});
    try{const endpoint=await new Promise((resolve,reject)=>{let stderr='';const timer=setTimeout(()=>reject(Error('Headless CDP startup timed out')),20000);child.once('error',error=>{clearTimeout(timer);reject(error);});child.once('exit',code=>{clearTimeout(timer);reject(Error('Headless Chromium exited '+code+': '+stderr.slice(-500)));});child.stderr.on('data',chunk=>{stderr+=chunk;const match=stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);if(match){clearTimeout(timer);resolve(match[1]);}});});
      const {connect}=await import('../linkedin');return {child,directory,connection:await connect(endpoint),origin:new URL(endpoint).origin.replace('ws:','http:')};
    }catch(error){child.kill();await rm(directory,{recursive:true,force:true});throw error;}
  })();return backupTestBrowser;
}
after(async()=>{if(!backupTestBrowser)return;const browser=await backupTestBrowser;browser.connection.close();browser.child.kill('SIGTERM');await new Promise(resolve=>browser.child.once('exit',resolve));await rm(browser.directory,{recursive:true,force:true,maxRetries:5,retryDelay:100});});
async function backupDom(html,{url}={}){
  const browser=await backupBrowser(),{connect,evaluate,BackupNode}=await import('../linkedin');const {targetId}=await browser.connection.call('Target.createTarget',{url:'about:blank',background:true});
  const tabs=await(await fetch(browser.origin+'/json/list')).json(),page=await connect(tabs.find(tab=>tab.id===targetId).webSocketDebuggerUrl);
  await page.call('Emulation.setFocusEmulationEnabled',{enabled:true});await page.call('Network.enable');await page.call('Network.setBlockedURLs',{urls:['https://*','http://*']});
  if(url){
    await page.call('Network.setBlockedURLs',{urls:[]});await page.call('Fetch.enable',{patterns:[{urlPattern:'*'}]});page.on(message=>{if(message.method==='Fetch.requestPaused')page.call('Fetch.fulfillRequest',{requestId:message.params.requestId,responseCode:200,responseHeaders:[{name:'content-type',value:'text/html'}],body:Buffer.from(message.params.resourceType==='Document'?html:'').toString('base64')}).catch(()=>{});});
    await page.call('Page.navigate',{url});for(let i=0;i<100;i++){if(await evaluate(page,'location.href==='+JSON.stringify(url)+'&&document.readyState!=="loading"&&Boolean(document.querySelector("main"))'))break;await new Promise(resolve=>setTimeout(resolve,10));}
  }else await evaluate(page,'document.open();document.write('+JSON.stringify('<base href="https://www.linkedin.com">'+html)+');document.close();');
  return {page,root:new BackupNode(page,null,20),evaluate:expression=>evaluate(page,expression),async close(){await browser.connection.call('Target.closeTarget',{targetId});page.close();}};
}

const BACKUP_SDUI_FIXTURE=String.raw`
<div id="post" componentkey="update-card-focus-post-token" role="listitem">
  <header>
    <button aria-label="Open control menu for post by Test Author"></button>
    <a href="https://www.linkedin.com/in/test-author/?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3Atest"><p><span aria-hidden="true">Test Author</span> • 1st</p></a>
    <p>Researcher and writer</p><p>2h • edited</p>
    <span aria-label="Test Author Verified Profile Premium"></span>
  </header>
  <div data-testid="expandable-text-box">First line<br>Second <a href="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fexample.org%2Fsafe%3Fa%3D1">safe link</a><button>more</button></div>
  <button aria-label="Reaction button state: no reaction"></button>
  <span id="reaction-count">12 reactions</span><span aria-labelledby="reaction-count"></span>
  <button aria-label="Comment">7</button><button aria-label="Repost">3</button>
  <a href="/analytics/post-summary/urn:li:activity:7510870387140857856/?trk=metrics">View analytics</a>
  <ul><li><svg id="praise-consumption-icon"></svg></li></ul>
  <img alt="View Test Author’s profile" src="https://media.licdn.com/profile-displayphoto/1">
  <img alt="View image" src="https://media.licdn.com/post/thumb-160" srcset="https://media.licdn.com/post/thumb-160 1x, https://media.licdn.com/post/full-1200 2x">
  <div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510958357751615490)">
    <header>
      <button aria-label="View more options for Commenter"></button>
      <a href="https://www.linkedin.com/in/commenter/?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3Acommenter"><p><span aria-hidden="true">Commenter</span> • 2nd</p><p>Commenter headline</p></a>
      <p>1d • edited</p><span aria-label="Commenter Verified Premium"></span>
    </header>
    <div data-testid="expandable-text-box">Comment<br>body <button>more</button></div>
    <button>4</button><span aria-label="Reacted to by the author"></span>
    <div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510960000000000000)">
      <header><button aria-label="View more options for Reply"></button><a href="https://www.linkedin.com/in/replier/"><p><span aria-hidden="true">Replier</span> • 3rd</p><p>Reply headline</p></a><p>3h</p></header>
      <div data-testid="expandable-text-box">Reply body</div><button>2</button>
    </div>
  </div>
</div>
`;

test('native SDUI backup retains author, text, media, badges, reactions and nested replies',async()=>{
 const {extractBackupSduiPost}=await import('../linkedin'),dom=await backupDom(BACKUP_SDUI_FIXTURE);
 try{const post=(await dom.root.all('#post'))[0],rows=await post.value(extractBackupSduiPost,{scrapedAt:'2026-10-04T00:00:00Z'}),[article,comment,reply]=rows;
 assert.equal(rows.length,3);assert.equal(article.authorName,'Test Author');assert.equal(article.authorMiniProfileUrn,'urn:li:fs_miniProfile:test');assert.equal(article.authorDescription,'Researcher and writer');assert.equal(article.content,'First line\nSecond safe link');assert.deepEqual(article.links,['https://example.org/safe?a=1']);assert.equal(article.reactionCount,12);assert.equal(article.commentCount,7);assert.equal(article.repostCount,3);assert.deepEqual(article.reactionTypesVisible,['celebrate']);assert.deepEqual(article.premiumVerifiedBadges,['premium','verified']);assert.equal(article.media[0].sources.at(-1),'https://media.licdn.com/post/full-1200');assert.equal(article.edited,true);assert.equal(article.postedText,'2h • edited');assert.equal(article.authorProfile,'https://www.linkedin.com/in/test-author/');
 assert.equal(comment.commenterName,'Commenter');assert.equal(comment.commenterMiniProfileUrn,'urn:li:fs_miniProfile:commenter');assert.equal(comment.commenterDescription,'Commenter headline');assert.equal(comment.commentedText,'1d • edited');assert.equal(comment.edited,true);assert.equal(comment.commenterDegree,'2nd');assert.equal(comment.content,'Comment\nbody');assert.equal(comment.reactedByAuthor,true);assert.equal(comment.reactionCount,4);assert.equal(reply.commenterName,'Replier');assert.equal(reply.parentCommentId,comment.id);
 }finally{await dom.close();}
});

test('native legacy backup still extracts full commentary and stable activity identity',async()=>{
 const {extractBackupPost}=await import('../linkedin'),dom=await backupDom('<div id="post" data-urn="urn:li:activity:7510870387140857856" role="article"><a class="update-components-actor__name" href="https://www.linkedin.com/in/example/">Example</a><div class="update-components-update-v2__commentary">Complete legacy content</div><div class="social-details-social-counts">12 reactions<br>3 comments<br>2 reposts</div></div>');
 try{const row=(await(await dom.root.all('#post'))[0].value(extractBackupPost,{scrapedAt:'2026-10-04T00:00:00Z'}))[0];assert.equal(row.id,'urn:li:activity:7510870387140857856');assert.equal(row.content,'Complete legacy content');assert.equal(row.commentCount,3);assert.equal(row.repostCount,2);}finally{await dom.close();}
});

test('native backup extracts usable video sources, poster and duration instead of blob thumbnails',async()=>{
 const {extractBackupSduiPost}=await import('../linkedin'),dom=await backupDom('<div id="post"><div data-vjs-player="true"><video></video></div></div>');
 try{await dom.evaluate(`document.querySelector('[data-vjs-player]').player={currentSources:()=>[{src:'blob:https://www.linkedin.com/temp',type:'video/mp4'},{src:'data:video/mp4;base64,temp',type:'video/mp4'},{src:'https://media.example/video.m3u8',type:'application/x-mpegURL'},{src:'https://media.example/video.mp4',type:'video/mp4'}],poster:()=>'https://media.example/poster.jpg',duration:()=>42}`);
 const row=(await(await dom.root.all('#post'))[0].value(extractBackupSduiPost,{scrapedAt:'2026-10-04T00:00:00Z',postUrn:'urn:li:activity:1'}))[0];assert.equal(row.media[0].url,'https://media.example/video.mp4');assert.equal(row.media[0].sources.length,2);assert.equal(row.media[0].poster,'https://media.example/poster.jpg');assert.equal(row.media[0].duration,42);
 }finally{await dom.close();}
});

test('native SDUI reposts distinguish the reposter from the original author and accept verified URNs',async()=>{
 const {extractBackupSduiPost}=await import('../linkedin'),dom=await backupDom('<div id="post"><div data-sdui-anchor-id="feed-header-repost"><a href="https://www.linkedin.com/in/reposter/">Reposter</a></div><header><button aria-label="Open control menu for post"></button><a href="https://www.linkedin.com/in/author/"><p>Author</p></a><p>Headline</p><p>1h</p><span aria-label="Visibility: Anyone"></span></header><div data-testid="expandable-text-box">Reposted content</div></div>');
 try{const row=(await(await dom.root.all('#post'))[0].value(extractBackupSduiPost,{scrapedAt:'2026-10-04T00:00:00Z',postUrn:'urn:li:activity:999'}))[0];assert.equal(row.id,'urn:li:activity:999');assert.equal(row.authorName,'Author');assert.equal(row.repostedBy,'Reposter');assert.equal(row.repostedByProfile,'https://www.linkedin.com/in/reposter/');}finally{await dom.close();}
});

const publicRepostCard=(id,content)=>`<div class="member-analytics-addon-entity-list__item"><a href="https://www.linkedin.com/in/person/"><span class="feed-mini-update-actor__name">Person</span></a><a href="https://www.linkedin.com/feed/update/urn:li:activity:${id}/">Post</a><a aria-label="View full post. ${content}"></a><span data-reaction-details>5</span></div>`;
test('native public repost extraction deduplicates identities and retains visible counts/body',async()=>{
 const {backupRepostsSnapshot}=await import('../linkedin'),dom=await backupDom('<main><h1>Reposts</h1>'+publicRepostCard('1','Full body')+publicRepostCard('1','Duplicate')+publicRepostCard('2','Second body')+'</main>');
 try{const rows=await dom.root.value(backupRepostsSnapshot);assert.equal(rows.length,2);assert.equal(rows[0].id,'urn:li:activity:1');assert.equal(rows[0].content,'Full body');assert.equal(rows[0].reactionCount,5);}finally{await dom.close();}
});

test('native DOM clicks deliver one event and keyed elements survive real sibling insertion/removal',async()=>{
 const dom=await backupDom('<div id="cards"><div componentkey="post-a">A</div><div componentkey="post-b">B</div></div><button id="click">Click</button>');
 try{await dom.evaluate(`window.clicks=0;document.querySelector('#click').onclick=()=>window.clicks++`);const button=(await dom.root.all('#click'))[0];await button.click();assert.equal(await dom.evaluate('window.clicks'),1);
 const pinned=(await dom.root.all('#cards [componentkey]'))[0];await dom.evaluate(`document.querySelector('#cards').innerHTML='<div componentkey="post-b">B</div><div componentkey="post-a">Hydrated A</div>'`);assert.equal(await pinned.value(el=>el.textContent),'Hydrated A');await dom.evaluate(`document.querySelector('[componentkey="post-a"]').remove()`);assert.equal(await pinned.value(el=>el.textContent),null);
 }finally{await dom.close();}
});

test('native permalink fallback restores clipboard methods and never writes to the user clipboard',async()=>{
 const {resolveBackupPostUrn}=await import('../linkedin'),dom=await backupDom('<div id="post"><button aria-label="Open control menu for post"></button></div>');
 try{await dom.evaluate(`window.originalCalls=0;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>window.originalCalls++}});window.originalWriteText=navigator.clipboard.writeText;document.querySelector('button').onclick=()=>{const p=document.createElement('p');p.textContent='Copy link to post';p.onclick=()=>navigator.clipboard.writeText('https://www.linkedin.com/feed/update/urn:li:activity:123456/');document.body.append(p);}`);
 assert.equal(await resolveBackupPostUrn((await dom.root.all('#post'))[0]),'urn:li:activity:123456');assert.equal(await dom.evaluate('window.originalCalls'),0);assert.equal(await dom.evaluate('navigator.clipboard.writeText===window.originalWriteText'),true);
 }finally{await dom.close();}
});

test('native UGC discovery rejects ambiguous React state and uses verified archive parents before menus',async()=>{
 const {backupUgcId,resolveBackupPostUrn}=await import('../linkedin'),dom=await backupDom('<div id="post"><button aria-label="Reaction button state: no reaction"></button></div>');
 try{await dom.evaluate(`document.querySelector('button').__reactFiberTest={memoizedProps:{triggers:[{value:'reactionState-urn:li:ugcPost:7415738265976221696'}]},pendingProps:{},return:null,stateNode:document.querySelector('#post')}`);const post=(await dom.root.all('#post'))[0];assert.equal(await post.value(backupUgcId),'urn:li:ugcPost:7415738265976221696');assert.equal(await resolveBackupPostUrn(post,{'urn:li:ugcPost:7415738265976221696':'urn:li:activity:7415939374598602752'}),'urn:li:activity:7415939374598602752');await dom.evaluate(`document.querySelector('button').__reactFiberTest.memoizedProps.triggers.push({value:'reactionState-urn:li:ugcPost:9999999999999999999'})`);assert.equal(await post.value(backupUgcId),'');}finally{await dom.close();}
});

test('native comment loaders wait for hydration and associate flat sibling replies with explicit parents',async()=>{
 const {loadBackupComments}=await import('../linkedin'),dom=await backupDom('<div id="post" componentkey="update-card-focus-fixture" role="listitem"><button aria-label="Comment">2</button><div componentkey="commentsSectionContainer"><div componentkey="CommentComponentReference_urn:li:comment:parent">Parent</div><button id="reply">Show replies</button></div></div>');
 try{await dom.evaluate(`document.querySelector('#reply').onclick=e=>{const button=e.currentTarget;setTimeout(()=>{button.insertAdjacentHTML('beforebegin','<div componentkey="CommentComponentReference_urn:li:comment:child">Delayed child</div>');button.remove();},30)}`);const stats=await loadBackupComments((await dom.root.all('#post'))[0],{maxRounds:12});assert.equal(stats.commentsLoaded,2);assert.equal(stats.replyParents['urn:li:comment:child'],'urn:li:comment:parent');assert.equal(stats.complete,true);}finally{await dom.close();}
});

test('native previous-comment role buttons expand delayed rows and report stuck loaders as incomplete',async()=>{
 const {loadBackupComments}=await import('../linkedin'),dom=await backupDom('<div id="post" componentkey="update-card-focus-fixture" role="listitem"><button aria-label="Comment">1</button><div componentkey="commentsSectionContainer"><div role="button" id="load">See previous comments</div></div></div>');
 try{await dom.evaluate(`document.querySelector('#load').onclick=e=>{const button=e.currentTarget;setTimeout(()=>{if(!button.isConnected)return;button.insertAdjacentHTML('beforebegin','<div componentkey="CommentComponentReference_urn:li:comment:late">Delayed comment</div>');button.remove();},5)}`);const post=(await dom.root.all('#post'))[0],stats=await loadBackupComments(post,{maxRounds:12});assert.equal(stats.commentsLoaded,1);assert.equal(stats.complete,true);await dom.evaluate(`document.querySelector('#post').insertAdjacentHTML('beforeend','<button>Load more comments</button>')`);const stuck=await loadBackupComments(post,{maxRounds:6});assert.equal(stuck.complete,false);assert.equal(stuck.remainingLoaders,1);}finally{await dom.close();}
});

test('native browser sessions create owned background targets with focus emulation and preserve borrowed tabs',async()=>{
 const browser=await backupBrowser(),client=new Client({cdp:browser.origin}),calls=[];const connection=await client.browserConnection(),call=connection.call.bind(connection);connection.call=(method,params)=>{calls.push({method,params});return call(method,params);};client.wait=async()=>{};
 try{const page=await client.background('about:blank');const {evaluate}=await import('../linkedin');assert.equal(await evaluate(page,'document.hasFocus()'),true);assert.ok(calls.some(row=>row.method==='Target.createTarget'&&row.params.background===true));assert.ok(!calls.some(row=>row.method==='Target.activateTarget'));}finally{await client.close();}
});

test('text facets OR all returned matching suggestions, deduplicate IDs, and keep different filters separate',async()=>{
 const {resolveSearchFacets}=await import('../linkedin'),calls=[];
 const result=await resolveSearchFacets(searchFacets({location:'Chennai,123',organization:'Tata','past-organization':'IBM',degree:'1,2'}),async(kind,query)=>{calls.push([kind,query]);return query==='Chennai'?[{id:'10',name:'Chennai, India'},{id:'11',name:'Greater Chennai Area'}]:query==='Tata'?[{id:'20',name:'Tata Consulting'},{id:'21',name:'Tata Motors'},{id:'20',name:'Tata Consulting'}]:[{id:'30',name:'IBM'},{id:'31',name:'An IBM Company'},{id:'32',name:'Red Hat'}];});
 assert.deepEqual(result.facets,[{key:'geoUrn',value:['10','11','123']},{key:'currentCompany',value:['20','21']},{key:'pastCompany',value:['30','31','32']},{key:'network',value:['F','S']}]);assert.equal(calls.length,3);assert.equal(result.selections.length,3);
 await assert.rejects(resolveSearchFacets(searchFacets({location:'Nowhere'}),async()=>[]),e=>e.code==='NOT_FOUND');
});

const typeaheadComponent=(id,name,group='currentCompany')=>['$','div',null,{componentkey:'row-'+id,children:[{bindingKey:{key:{value:{id:'SearchResults_testFILTER_ITEM_'+group+'_'+id+'_CHECKED'}}}},{textProps:{children:[name]}}]}];
test('typeahead decoding scopes labels to their identity and rejects invalid/error streams',async()=>{
 const {decodeFacetTypeahead,typeaheadRequest}=await import('../linkedin');
 const stream='0:'+JSON.stringify({response:{errors:[]}})+'\n1:'+JSON.stringify(typeaheadComponent('1','Tata Consulting'))+'\n2:'+JSON.stringify(typeaheadComponent('2','Tata Motors'))+'\n3:I["module",[],"Typeahead"]\n';
 assert.deepEqual(decodeFacetTypeahead(stream,'company'),[{id:'1',name:'Tata Consulting'},{id:'2',name:'Tata Motors'}]);assert.deepEqual(decodeFacetTypeahead('0:{"response":{"errors":[]}}','geo'),[]);assert.throws(()=>decodeFacetTypeahead('unknown','geo'),e=>e.code==='SCHEMA_CHANGED');assert.throws(()=>decodeFacetTypeahead('0:{"response":{"errors":["error"]}}','geo'),e=>e.code==='ENDPOINT_CHANGED');
 const body=typeaheadRequest('geo','Chennai ")雪');assert.equal(body.states[0].value,'Chennai ")雪');assert.equal(body.requestId,'com.linkedin.sdui.search.filters.requests.FiltersLocationTypeaheadRequest');assert.throws(()=>typeaheadRequest('write','x'));
});

test('resolved text filters are cached per account, displayed, and reused offline without a browser',async()=>{
 const f=fixture();let received;const lookups=[];
 const factory=()=>({...f.factory(),async typeahead(kind,query){lookups.push([kind,query]);return [{id:'1',name:query+' Central'},{id:'2',name:'Greater '+query}];},async search(kind,query,cursor,size,facets){received=facets;return{records:[{id:'p',kind:'profile',name:'Reader'}],next:null,source:'test'};}});
 const args=['people','engineer','--location','Chennai','--organization','IBM,Tata','--past-organization','IBM','--db',f.path];
 try{const live=await run(args,{clientFactory:factory,log(){}});assert.equal(live.result.meta.resolved_filters.length,4);assert.equal(lookups.length,3);assert.deepEqual(received.map(f=>f.value),[['1','2'],['1','2'],['1','2']]);assert.match(render(live.result,'md',undefined,live.options),/Greater Chennai/);
 const offline=await run([...args,'--offline'],{clientFactory(){throw Error('Must not open browser');}});assert.equal(offline.result.data[0].name,'Reader');assert.equal(offline.result.meta.resolved_filters[0].query,'Chennai');
 const c=new Cache(f.path);c.useAccount('other','other');c.close();await assert.rejects(run([...args,'--offline','--account','other'],{clientFactory(){throw Error('Must not open browser');}}),e=>e.code==='CACHE_MISS');
 }finally{f.clean();}
});

test('profile, activity and backup accept a name and choose the first personalized valid person',async()=>{
 const f=fixture(),queries=[],profileArgs=[],backupArgs=[];const chosen={id:'chosen',kind:'profile',name:'First Last',username:'chosen-person',url:'https://www.linkedin.com/in/chosen-person/'};
 const factory=()=>({...f.factory(),async search(kind,query){queries.push([kind,query]);return{records:[chosen,{...chosen,username:'second',url:'https://www.linkedin.com/in/second/'}],next:null};},async profile(value){profileArgs.push(value);return chosen;},async activity(owner){assert.equal(owner.id,'chosen');return{records:[{id:'post',kind:'post',text:'Activity'}],next:null,source:'test'};},async*backupPosts(username){backupArgs.push(username);}});
 try{const activity=await run(['activity','First Last','--db',f.path],{clientFactory:factory,log(){}});assert.equal(activity.result.meta.resolved_profile.identifier,'chosen-person');assert.equal(profileArgs[0],'chosen-person');assert.deepEqual(queries,[['people','First Last']]);
 const offline=await run(['profile','First Last','--offline','--db',f.path],{clientFactory(){throw Error('No browser');}});assert.equal(offline.result.data.name,'First Last');
 await run(['backup','First Last','--archive',join(f.dir,'archive.jsonl'),'--db',f.path],{clientFactory:factory,log(){}});assert.deepEqual(backupArgs,['chosen-person']);assert.equal(queries.length,1);
 await run(['profile','name:Alice','--db',f.path],{clientFactory:factory,log(){}});assert.equal(queries.at(-1)[1],'Alice');
 }finally{f.clean();}
});

test('explicit identities bypass people lookup and missing names/filters fail rather than broadening the query',async()=>{
 const {profileTarget,resolveProfileTarget}=await import('../linkedin');assert.deepEqual(profileTarget('https://www.linkedin.com/in/example/'),{identifier:'example'});assert.deepEqual(profileTarget('example'),{identifier:'example'});assert.deepEqual(profileTarget('First Last'),{query:'First Last'});assert.throws(()=>profileTarget('https://linkedin.com.evil/in/person'));
 assert.equal((await resolveProfileTarget('example',()=>{throw Error('Must not search');})).identifier,'example');await assert.rejects(resolveProfileTarget('No Person',async()=>[]),e=>e.code==='NOT_FOUND');
});

test('posts put timestamps first and infer missing publication time from stable activity IDs',()=>{
 const id='urn:li:activity:'+String(BigInt(Date.parse('2026-11-09T10:30:00Z'))<<22n),record={kind:'post',id,author:{name:'Author',headline:'A long headline'},text:'Body'};
 const output=render({ok:true,data:record},'md',undefined,mdContext('post'));assert.match(output,/\nPublished: /);assert.doesNotMatch(output,/from activity ID/);assert.ok(output.indexOf('Published:')<output.indexOf('Body'));
});

test('interactive Markdown prefers glow -p, falls back to PAGER, and leaves pipes/raw fallback untouched',async()=>{
 const {presentMarkdown}=await import('../linkedin'),dir=await mkdtemp(join(tmpdir(),'linkedin-pager-')),capture=join(dir,'viewer.json');
 // The executable fixture uses CommonJS and an async function so it needs no package metadata.
 const program='#!'+process.execPath+'\n(async()=>{let text="";for await(const c of process.stdin)text+=c;require("node:fs").writeFileSync(process.env.VIEWER_CAPTURE,JSON.stringify({args:process.argv.slice(2),text}));})();\n';
 const writes=[],stream={isTTY:true,write(value){writes.push(value);}};
 try{await writeFile(join(dir,'glow'),program,{mode:0o755});await writeFile(join(dir,'pager'),program,{mode:0o755});let env={...process.env,PATH:dir,VIEWER_CAPTURE:capture,PAGER:"'"+join(dir,'pager')+"' --plain"};
 presentMarkdown('# Report\n',{stream,env});assert.deepEqual(JSON.parse(await readFile(capture,'utf8')),{args:['-p'],text:'# Report\n'});
 await rm(join(dir,'glow'));presentMarkdown('# Pager\n',{stream,env});assert.deepEqual(JSON.parse(await readFile(capture,'utf8')),{args:['--plain'],text:'# Pager\n'});
 presentMarkdown('# Raw\n',{stream,env:{...env,PAGER:''}});assert.equal(writes.at(-1),'# Raw\n');presentMarkdown('# Pipe\n',{stream:{isTTY:false,write:value=>writes.push(value)},env});assert.equal(writes.at(-1),'# Pipe\n');
 }finally{await rm(dir,{recursive:true,force:true});}
});

test('cache schema migration preserves old records and persists account-scoped input lookups',async()=>{
 const f=fixture();try{let c=new Cache(f.path);c.useAccount('a');c.commit('a','posts',[{id:'p',kind:'post',text:'Original'}],null);c.db.exec('PRAGMA user_version=1');c.close();c=new Cache(f.path);assert.equal(c.get('a','p').text,'Original');c.saveLookup('a','geo','Chennai',[{id:'1',name:'Chennai'}]);assert.equal(c.lookup('a','geo','CHENNAI').data[0].id,'1');assert.equal(c.lookup('b','geo','Chennai'),null);c.close();}finally{f.clean();}
});

test('connections retain unavailable members without losing the rest of the page or cached names',async()=>{
 const {decodeNetwork}=await import('../linkedin');const profile={entityUrn:'urn:li:fsd_profile:known',firstName:'Known',lastName:'Person'},payload={data:{'*elements':['c1','c2'],paging:{total:2}},included:[profile,{entityUrn:'c1','*connectedMemberResolutionResult':profile.entityUrn,createdAt:1},{entityUrn:'c2',connectedMember:'urn:li:fsd_profile:unavailable',createdAt:2}]};
 const decoded=decodeNetwork(payload,'connections',{start:0,count:2});assert.equal(decoded.records.length,2);assert.equal(decoded.records[1].unavailable,true);assert.equal(decoded.records[1].connectedAt,2);assert.equal(decoded.warnings.length,1);
 const c=new Cache(':memory:');try{c.commit('a','old',[{id:'urn:li:fsd_profile:unavailable',kind:'profile',name:'Previously known'}],null);c.commit('a','connections',decoded.records,null);assert.equal(c.get('a','urn:li:fsd_profile:unavailable').name,'Previously known');}finally{c.close();}
 assert.throws(()=>decodeNetwork({data:{'*elements':['x']},included:[{entityUrn:'x'}]},'connections',{start:0,count:1}),e=>e.code==='SCHEMA_CHANGED');
});

test('paths reports effective locations and configuration without credentials, browser or database writes',async()=>{
 const {existsSync}=await import('node:fs');const dir=await mkdtemp(join(tmpdir(),'linkedin-paths-')),db=join(dir,'not-created','cache.sqlite'),archive=join(dir,'posts.jsonl');
 try{const response=await run(['paths','--db',db,'--archive',archive],{clientFactory(){throw Error('Must not open browser');}});assert.equal(response.result.data.cacheDatabase,db);assert.equal(response.result.data.backupArchive,archive);assert.equal(response.result.data.backupLock,archive+'.lock');assert.match(response.result.data.configFile,/None/);assert.equal(existsSync(db),false);assert.match(render(response.result,'md',undefined,response.options),/^# LinkedIn paths/);}finally{await rm(dir,{recursive:true});}
});

test('native session cleanup closes every owned socket and browser socket after a target-close failure',async()=>{
 const client=new Client(),closed=[],targets=[];client.json=async()=>[];client.page={close(){closed.push('borrowed');}};client.owned=[{id:'one',page:{close(){closed.push('one');}}},{id:'two',page:{close(){closed.push('two');}}}];client.browser={async call(method,{targetId}){targets.push(targetId);if(targetId==='two')throw Error('Target disappeared');},close(){closed.push('browser');}};
 await assert.rejects(client.close(),/Target disappeared/);assert.deepEqual(new Set(closed),new Set(['borrowed','one','two','browser']));assert.deepEqual(targets,['two','one']);
});

test('native profile lookup bootstrap uses an existing LinkedIn tab and does not close the borrowed target',async()=>{
 const dom=await backupDom('<main>Borrowed tab</main>'),browser=await backupBrowser(),tabs=await(await fetch(browser.origin+'/json/list')).json(),tab=tabs.find(t=>t.type==='page'&&t.url==='about:blank'),client=new Client({cdp:browser.origin});
 client.json=async()=>[{...tab,url:'https://www.linkedin.com/feed/'}];client.background=async()=>{throw Error('Must reuse the existing tab');};try{await client.open();assert.equal(client.owned.length,0);await client.close();assert.ok((await(await fetch(browser.origin+'/json/list')).json()).some(t=>t.id===tab.id));}finally{await dom.close();}
});

test('native bootstrap creates a background source if no LinkedIn tab is open and validates loopback endpoints',async()=>{
 const client=new Client();client.json=async()=>[{type:'page',url:'https://example.com'}];let url;const page={close(){}};client.background=async value=>{url=value;return page;};await client.open();assert.equal(url,'https://www.linkedin.com/feed/');assert.equal(client.page,page);
 for(const cdp of ['https://localhost:9222','http://example.com:9222','ws://localhost:9222/page'])assert.throws(()=>new Client({cdp}),e=>e.code==='INVALID_INPUT');
});

test('native backup dates preserve Snowflake precision, relative periods, exclusive until and dry-run file safety',async()=>{
 const when='2026-08-14T12:00:00.000Z',id='urn:li:activity:'+String(BigInt(Date.parse(when))<<22n),row=backupTimeFields({type:'post',id,postedText:'1d'},'2026-08-15T12:00:00Z');assert.equal(row.postedAt,when);assert.equal(row.postedAtConfidence,'id');
 const now=new Date('2026-10-04T12:00:00Z');for(const[value,days]of [['7d',7],['1y',365],['2 months ago',60]])assert.equal(sinceDate(value,now),new Date(now.getTime()-days*86400000).toISOString());assert.equal(sinceDate('2026-09-01',now),'2026-09-01T00:00:00.000Z');
 const author={...row,authorProfile:'https://www.linkedin.com/in/example/'};assert.equal(selectBackupPosts([author],'example',{until:when}).length,0);
 const {existsSync}=await import('node:fs'),dir=await mkdtemp(join(tmpdir(),'linkedin-backup-preview-')),file=join(dir,'archive.jsonl'),db=join(dir,'db.sqlite');try{const response=await run(['backup','me','--analytics','--since','7d','--archive',file,'--db',db,'--dry-run'],{clientFactory(){throw Error('Must not open browser');}});assert.equal(response.result.meta.dry_run,true);assert.equal(existsSync(db),false);assert.equal(existsSync(file),false);assert.equal(existsSync(file+'.lock'),false);}finally{await rm(dir,{recursive:true});}
});

test('native backup reply inference requires an observed parent and a complete sibling group',()=>{
 const noMapping=[{type:'comment',id:'p',replyCount:2},{type:'comment',id:'a'},{type:'comment',id:'b'}];applyBackupReplyParents(noMapping,{});assert.equal(noMapping[1].parentCommentId,undefined);
 const incomplete=[{type:'comment',id:'p',replyCount:3},{type:'comment',id:'a'},{type:'comment',id:'b'}];applyBackupReplyParents(incomplete,{b:'p'});assert.equal(incomplete[1].parentCommentId,undefined);assert.equal(incomplete[2].parentCommentId,'p');
});

test('native detailed analytics handles misleading Discovery text, sparse viewers, video, withholding and delayed zero',async()=>{
 const {waitBackupAnalytics}=await import('../linkedin'),id='urn:li:activity:7510870387140857856';
 const prefix='Post mentions Discovery\n9 work at Warner Bros. Discovery\nDiscovery\n100\nImpressions\nVideo performance\n4,661\nVideo views\nWatch time\n19h 40m\nAverage watch time\n15s\nWho’s viewed your profile since this post\nView\nAlice\nResearcher\nBob\nEngineer\nDon’t miss out\nTop demographics\nAnalytics & tools';
 const record=parseDetailedBackupAnalytics({text:prefix,url:'https://www.linkedin.com/analytics/post-summary/'+id+'/'},id);assert.equal(record.analytics.impressionCount,100);assert.deepEqual(record.analytics.profileViewerSummary,['Alice','Researcher','Bob','Engineer']);assert.deepEqual(record.analytics.videoPerformance,{views:4661,watchTime:'19h 40m',averageWatchTime:'15s'});assert.equal(record.analytics.inNetworkPercent,null);
 const body='Discovery\n10\nImpressions\nEngagement\nSends on LinkedIn\n';assert.equal(parseDetailedBackupAnalytics({text:body,url:'x'},id),null);assert.equal(parseDetailedBackupAnalytics({text:body+'–',url:'x'},id).analytics.sendCount,null);
 const snapshots=[...Array.from({length:6},()=>({text:body+'0',loading:true})),{text:body},{text:body+'0',loading:false}];let calls=0;
 const page={async call(){const snapshot=snapshots[Math.min(calls++,snapshots.length-1)];return{result:{value:{url:'https://www.linkedin.com/analytics/post-summary/'+id+'/',...snapshot}}};}};
 const ready=await waitBackupAnalytics({timeout:6000},page,id);assert.equal(ready.analytics.sendCount,0);assert.ok(calls>=3);
});

test('native detailed analytics follows the actual public-reposts link and preserves richer duplicate rows',async()=>{
 const id='urn:li:activity:7510870387140857856',url='https://www.linkedin.com/analytics/post-summary/'+id+'/',repostUrl='https://www.linkedin.com/feed/update/'+id+'/?resultType=RESHARES';
 const source=await backupDom('<main>Discovery<br>100<br>Impressions<br>Engagement<br>Reactions<br>5<br>Comments<br>0<br>Reposts<br>2<br>No demographic data<a href="'+repostUrl+'">Reposts</a></main>',{url});
 const target=await backupDom('<main><h1>Reposts</h1>'+publicRepostCard('1','Rich original body')+'<div style="height:2000px"></div></main>');
 try{await target.evaluate(`window.addEventListener('scroll',()=>{if(window.added)return;window.added=true;document.querySelector('[aria-label^="View full post."]').setAttribute('aria-label','View full post. ');document.querySelector('main').insertAdjacentHTML('beforeend',${JSON.stringify(publicRepostCard('2','Second body'))});})`);
 const client=new Client({timeout:5000});client.whoami=async()=>({username:'example'});client.analytics=async()=>{client.analyticsPage=source.page;};let opened;client.background=async value=>{opened=value;return target.page;};
 const row=await client.backupAnalytics({id,authorProfile:'https://www.linkedin.com/in/example/'},{maxScrolls:4,settleMs:0});assert.equal(opened,repostUrl);assert.equal(row.reposts.length,2);assert.equal(row.reposts[0].content,'Rich original body');assert.equal(row.repostScrapeStats.complete,true);
 }finally{await source.close();await target.close();}
});

test('native analytics zero reposts skips list navigation and missing/private rows remain incomplete',async()=>{
 const id='urn:li:activity:7510870387140857856',url='https://www.linkedin.com/analytics/post-summary/'+id+'/',repostUrl='https://www.linkedin.com/feed/update/'+id+'/?resultType=RESHARES';
 for(const expected of [0,3]){
  const source=await backupDom('<main>Discovery<br>100<br>Impressions<br>Engagement<br>Reactions<br>0<br>Comments<br>0<br>Reposts<br>'+expected+'<br>No demographic data'+(expected?'<a href="'+repostUrl+'">Reposts</a>':'')+'</main>',{url});const target=expected?await backupDom('<main><h1>Reposts</h1>'+publicRepostCard('1','Visible public repost')+'</main>'):null;
  try{const client=new Client({timeout:5000});client.whoami=async()=>({username:'example'});client.analytics=async()=>{client.analyticsPage=source.page;};let navigations=0;client.background=async()=>{navigations++;assert.ok(target);return target.page;};const row=await client.backupAnalytics({id,authorProfile:'https://www.linkedin.com/in/example/'},{maxScrolls:4,settleMs:0});assert.equal(row.repostScrapeStats.loaded,expected?1:0);assert.equal(row.repostScrapeStats.complete,!expected);assert.equal(row.repostScrapeStats.excludesPrivate,true);assert.equal(navigations,expected?1:0);}finally{await source.close();if(target)await target.close();}
 }
});

const scheduledDescriptor={feedUpdateUrn:'urn:li:ugcPost:1234567890123456789',scheduledAtEpochMillis:'1794298500000'};
const scheduledListFixture=items=>'0:'+JSON.stringify({items})+'\n';
function scheduledFullFixture(row,text){const root=['$','div',null,{componentKey:'ScheduledPostRowSlot_'+row.feedUpdateUrn,children:['$','div',null,{viewTrackingSpecs:{viewName:'feed-commentary'},textProps:{children:['$1']}}]}];return '0:'+JSON.stringify(root)+'\n1:T'+Buffer.byteLength(text).toString(16)+','+text;}
test('scheduled components decode exact timestamps and full Unicode/multiline contents without reading action payloads',async()=>{
 const {decodeScheduledList,decodeScheduledPost,readRscRows,scheduledRequest}=await import('../linkedin');const text='A queued post 🧪\n\n'+('Long content 雪. '.repeat(200));const second={feedUpdateUrn:'urn:li:share:2222222222222222222',scheduledAtEpochMillis:'1794532500000'};
 assert.deepEqual(decodeScheduledList(scheduledListFixture([second,scheduledDescriptor])),[scheduledDescriptor,second]);const post=decodeScheduledPost(scheduledFullFixture(scheduledDescriptor,text),scheduledDescriptor);assert.equal(post.text,text.trim());assert.equal(post.scheduledAt,'2026-11-10T08:15:00.000Z');assert.equal(post.kind,'scheduled');assert.equal(decodeScheduledPost(scheduledFullFixture(scheduledDescriptor,'$1\nLiteral dollars $$5'),scheduledDescriptor).text,'$1\nLiteral dollars $$5');assert.deepEqual(decodeScheduledList(scheduledListFixture([])),[]);
 assert.throws(()=>readRscRows('0:T10,short'),e=>e.code==='SCHEMA_CHANGED');assert.throws(()=>scheduledRequest({...scheduledDescriptor,feedUpdateUrn:'invalid'}),e=>e.code==='INVALID_INPUT');assert.throws(()=>decodeScheduledPost(scheduledFullFixture(second,text),scheduledDescriptor),e=>e.code==='SCHEMA_CHANGED');
 const unknown=decodeScheduledPost('0:'+JSON.stringify({componentKey:'ScheduledPostRowSlot_'+scheduledDescriptor.feedUpdateUrn}),scheduledDescriptor);assert.equal(unknown.text,undefined);assert.equal(unknown.warnings.length,1);
 const output=render({ok:true,data:[post]},'md',undefined,mdContext('scheduled'));assert.match(output,/Scheduled posts/);assert.match(output,/10 Nov 2026/);assert.ok(output.indexOf('Scheduled:')<output.indexOf('A queued post'));assert.doesNotMatch(output,/Published:/);
});

test('scheduled reads only allow registered components and bound body requests by limit',async()=>{
 const client=new Client(),{decodeScheduledList}=await import('../linkedin');const calls=[];client.sduiRead=async body=>{calls.push(body);return body.componentId.endsWith('scheduledPostsList')?scheduledListFixture([scheduledDescriptor,{...scheduledDescriptor,feedUpdateUrn:'urn:li:share:2222222222222222222'}]):scheduledFullFixture(body.clientArguments.payload,'Queued contents');};
 const response=await client.scheduled({limit:1});assert.equal(response.records.length,1);assert.equal(response.total,2);assert.equal(calls.length,2);assert.equal(calls[1].clientArguments.states[0].value,'Self');
 const real=new Client();await assert.rejects(real.sduiRead({requestId:'delete-post'}),e=>e.code==='INVALID_INPUT');
});

test('scheduled cache snapshots remove cancelled posts and limited snapshots cannot hide unfetched posts',async()=>{
 const f=fixture();let posts=[{id:'s1',kind:'scheduled',scheduledAt:'2026-11-10T08:15:00Z',text:'First'},{id:'s2',kind:'scheduled',scheduledAt:'2026-11-13T01:15:00Z',text:'Second'}],reads=0;
 const factory=()=>({...f.factory(),async scheduled({limit}){reads++;return{records:posts.slice(0,limit),total:posts.length};}});
 try{const partial=await run(['scheduled','--limit','1','--db',f.path],{clientFactory:factory,log(){}});assert.equal(partial.result.data.length,1);
 const partialOffline=await run(['scheduled','--offline','--db',f.path],{clientFactory(){throw Error('No browser');}});assert.match(partialOffline.result.warnings[0],/1 of 2/);
 const full=await run(['scheduled','--db',f.path],{clientFactory:factory,log(){}});assert.equal(full.result.data.length,2);assert.equal(reads,2);
 const offline=await run(['scheduled','--offline','--db',f.path],{clientFactory(){throw Error('No browser');}});assert.equal(offline.result.data.length,2);
 posts=[];await run(['scheduled','--refresh','--db',f.path],{clientFactory:factory,log(){}});const empty=await run(['scheduled','--offline','--db',f.path],{clientFactory(){throw Error('No browser');}});assert.deepEqual(empty.result.data,[]);assert.match(render(empty.result,'md',undefined,empty.options),/No scheduled posts/);
 }finally{f.clean();}
});

test('native short permalinks follow a bounded HEAD redirect and restore clipboard interception',async()=>{
 const {resolveBackupPostUrn}=await import('../linkedin'),dom=await backupDom('<div id="post"><button aria-label="Open control menu for post"></button></div>'),originalFetch=globalThis.fetch,requests=[];
 try{await dom.evaluate(`window.originalCalls=0;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>window.originalCalls++}});window.originalWriteText=navigator.clipboard.writeText;document.querySelector('button').onclick=()=>{const p=document.createElement('p');p.textContent='Copy link to post';p.onclick=()=>navigator.clipboard.writeText('https://lnkd.in/test');document.body.append(p);}`);
 globalThis.fetch=async(url,options)=>{if(url!=='https://lnkd.in/test')return originalFetch(url,options);requests.push({url,method:options.method,hasTimeout:Boolean(options.signal)});return{url:'https://www.linkedin.com/feed/update/urn:li:activity:123456/'};};
 assert.equal(await resolveBackupPostUrn((await dom.root.all('#post'))[0]),'urn:li:activity:123456');assert.deepEqual(requests,[{url:'https://lnkd.in/test',method:'HEAD',hasTimeout:true}]);assert.equal(await dom.evaluate('window.originalCalls'),0);assert.equal(await dom.evaluate('navigator.clipboard.writeText===window.originalWriteText'),true);
 }finally{globalThis.fetch=originalFetch;await dom.close();}
});

test('machine post records carry inferred publication timestamps and the help documents human lookup/viewer behavior',async()=>{
 const {postRecord,helpText}=await import('../linkedin'),when='2026-11-09T10:30:00.000Z',id='urn:li:activity:'+String(BigInt(Date.parse(when))<<22n);const record=postRecord({metadata:{backendUrn:id},commentary:{text:'Body'}});assert.equal(record.publishedAt,when);assert.equal(record.publishedAtConfidence,'id');const help=helpText();for(const text of ['Chennai','Tata','first accessible','glow -p','$PAGER','scheduled','paths'])assert.ok(help.includes(text),text);
});

test('post Markdown has a three-line header without redundant profile or Post labels',()=>{
 const output=render({ok:true,data:mdPost},'md',undefined,mdContext('post'));
 const lines=output.split('\n');assert.match(lines[0],/^# Post by Ada Rao$/);assert.match(lines[1],/^Published: .* · Researcher\s*$/);assert.equal(lines[2],mdPost.url);assert.doesNotMatch(output,/Author:|Profile:|Post: /);
 const list=render({ok:true,data:[mdPost,{...mdPost,id:'other'}]},'md',undefined,mdContext('feed'));assert.match(list,/## Post by Ada Rao\nPublished: .*\nhttps:/);
 assert.doesNotMatch(list,/Author:/);
 const named=render({ok:true,data:[{...mdPost,name:'A custom title'}]},'md',undefined,mdContext('feed'));assert.match(named,/## A custom title\nPublished: .* · Author: Ada Rao/);
 for(const name of ['Ada Rao','Ben Shah']){
 const repost=render({ok:true,data:{...mdPost,resharedPost:{...mdPost,author:{name}}}},'md',undefined,mdContext('post'));assert.equal((repost.match(/Author:/g)??[]).length,1);assert.ok(repost.includes('Author: '+name));
 }
 const activity=render({ok:true,data:{kind:'activity',actor:{name:'Ben'},post:mdPost}},'md',undefined,mdContext('activity'));assert.match(activity,/Author: Ada Rao/);
});

test('native author lists omit keywords, OR identities and request latest',async()=>{
 const client=new Client();let captured;client.gql=async(id,args)=>{captured=args;return {data:{data:{searchDashClustersByAll:{elements:[],paging:{total:0}}}}};};
 await client.authorPosts([{id:'urn:li:fsd_profile:one',kind:'profile'},{id:'urn:li:fsd_profile:two',kind:'profile'},{id:'urn:li:fsd_company:123',kind:'company'}],null,5);
 assert.equal(captured.query.keywords,undefined);assert.deepEqual(captured.query.queryParameters,[{key:'resultType',value:['CONTENT']},{key:'fromMember',value:['one','two']},{key:'fromOrganization',value:['123']},{key:'sortBy',value:['date_posted']}]);
});

test('activity usernames try profiles, fall back to exact companies, and names search people',async()=>{
 const f=fixture(),calls=[];const factory=()=>({...f.factory(),async profile(value){calls.push('profile:'+value);if(value==='openai'||value==='Alice')throw Object.assign(Error('Missing profile'),{code:value==='openai'?'FORBIDDEN':'NOT_FOUND'});return {id:'urn:li:fsd_profile:'+value,kind:'profile',username:value,name:value,url:'https://www.linkedin.com/in/'+value+'/'};},async company(value){calls.push('company:'+value);if(value!=='openai')throw Object.assign(Error('Missing company'),{code:'NOT_FOUND'});return{id:'urn:li:fsd_company:123',kind:'company',name:'OpenAI',url:'https://www.linkedin.com/company/openai/'};},async search(){calls.push('search');return{records:[{url:'https://www.linkedin.com/in/alice-person/',name:'Alice Person'}]};},async activity(){return{records:[{id:'post',kind:'post',text:'Body'}],next:null};},async authorPosts(actors){assert.equal(actors[0].kind,'company');return{records:[{id:'company-post',kind:'post',text:'Company body'}],next:null};}});
 try{await run(['activity','sanand0','--db',f.path],{clientFactory:factory,log(){}});assert.deepEqual(calls,['profile:sanand0']);calls.length=0;
 await run(['activity','openai','--db',f.path],{clientFactory:factory,log(){}});assert.deepEqual(calls,['profile:openai','company:openai']);calls.length=0;
 await run(['activity','Alice','--db',f.path],{clientFactory:factory,log(){}});assert.deepEqual(calls,['profile:Alice','company:Alice','search','profile:alice-person']);calls.length=0;
 await run(['activity','https://www.linkedin.com/company/openai/home','--db',f.path],{clientFactory:factory,log(){}});assert.deepEqual(calls,['company:openai']);
 }finally{f.clean();}
});

test('multiple activity profiles use one native list, sort before limiting, and work offline',async()=>{
 const f=fixture();let requests=0;const factory=()=>({...f.factory(),async profile(value){return{id:'urn:li:fsd_profile:'+value,kind:'profile',username:value,name:value};},async authorPosts(actors){requests++;assert.equal(actors.length,2);return{records:[{id:'old',kind:'post',publishedAt:'2026-01-01'},{id:'new',kind:'post',publishedAt:'2026-11-01'}],next:null,source:'voyager'};}});
 try{const args=['activity','sanand0','ramar','--limit','1','--db',f.path];const response=await run(args,{clientFactory:factory,log(){}});assert.equal(response.result.data[0].id,'new');assert.equal(requests,1);
 const offline=await run([...args,'--offline'],{clientFactory(){throw Error('No browser');}});assert.equal(offline.result.data[0].id,'new');
 assert.throws(()=>parse(['activity','one','two','--kind','comments']),e=>e.code==='INVALID_INPUT');
 }finally{f.clean();}
});

test('feed distinguishes collapse controls from unexpanded text and hydrates embedded reposts',async()=>{
 const {feedCards}=await import('../linkedin');const dom=await backupDom(`<div data-urn="urn:li:activity:1" role="article"><div data-testid="expandable-text-box">Full text<button aria-label="see less">less</button><button aria-hidden="true">… more</button></div><div data-testid="expandable-text-box">Original text</div></div><div data-urn="urn:li:activity:2" role="article"><div data-testid="expandable-text-box">Short text<button aria-label="see more">… more</button></div></div>`);
 try{const snapshot=await dom.root.value(feedCards);assert.equal(snapshot.records[0].textTruncated,false);assert.equal(snapshot.records[0].text,'Full text');assert.equal(snapshot.records[1].textTruncated,true);assert.deepEqual(snapshot.hydrate,['urn:li:activity:1','urn:li:activity:2']);
 const client=new Client();client.feedPage=dom.page;client.wait=async()=>{};const hydrated=[];client.post=async id=>{hydrated.push(id);return{id,kind:'post',text:'API full text',textTruncated:false,...(id.endsWith(':1')?{resharedPost:{text:'API original text'}}:{})};};
 const page=await client.feed(null,2);assert.equal(page.records[0].resharedPost.text,'API original text');assert.ok(page.records.every(post=>!post.textTruncated));assert.equal(hydrated.length,2);
 }finally{await dom.close();}
});

test('post decoder accepts direct legacy reshares and metadata identity without infinite cycles',async()=>{
 const {postRecord}=await import('../linkedin');const original={updateMetadata:{urn:'urn:li:activity:22'},actor:{name:'Original'},commentary:{text:'Original body'}};
 const record=postRecord({updateMetadata:{urn:'urn:li:activity:33'},actor:{name:'Reposter'},commentary:{text:'My comment'},resharedUpdate:original});assert.equal(record.id,'urn:li:activity:33');assert.equal(record.resharedPost.text,'Original body');assert.equal(record.resharedPost.url,'https://www.linkedin.com/feed/update/urn:li:activity:22/');
 const wrapped=postRecord({metadata:{backendUrn:'urn:li:activity:33'},resharedUpdate:{'*update':'original'}},ref=>ref==='original'?original:ref);assert.equal(wrapped.resharedPost.text,'Original body');
 original.resharedUpdate=original;assert.doesNotThrow(()=>postRecord(original));
 const c=new Client();c.api=async()=>({data:{'*value':'media'},included:[{entityUrn:'media',actor:{name:'Author'},content:{url:'https://example.com/image.jpg'}}]});assert.equal((await c.post('urn:li:activity:33')).text,'');
});

test('activity validates explicit types, propagates auth/rate/schema errors, and keeps profile precedence',async()=>{
 const {activityTarget,resolveActivityTarget}=await import('../linkedin');assert.deepEqual(activityTarget('https://www.linkedin.com/company/openai/home'),{company:'openai'});assert.deepEqual(activityTarget('urn:li:company:123'),{company:'123'});assert.throws(()=>activityTarget('https://linkedin.com.evil/company/openai'));assert.throws(()=>activityTarget('https://www.linkedin.com/company/'));
 for(const code of ['AUTH_REQUIRED','RATE_LIMITED','NETWORK_ERROR','SCHEMA_CHANGED'])await assert.rejects(resolveActivityTarget('someone',{profile(){throw Object.assign(Error('Failure'),{code});},company(){throw Error('Must not try company');}},()=>{throw Error('Must not search');}),e=>e.code===code);
 await assert.rejects(resolveActivityTarget('https://www.linkedin.com/in/missing/',{profile(){throw Object.assign(Error('Missing'),{code:'NOT_FOUND'});},company(){throw Error('Must not try company');}},()=>{throw Error('Must not search');}),e=>e.code==='NOT_FOUND');
 const person={kind:'profile',id:'person'};assert.equal(await resolveActivityTarget('openai',{async profile(){return person;},company(){throw Error('Profile must win');}},()=>[]),person);
});

test('company decoder handles numeric URLs, missing slugs and normalized roots',async()=>{
 const c=new Client();let path;c.api=async p=>{path=p;return{data:{entityUrn:'urn:li:fsd_company:123',name:'Example',universalName:'example'}};};assert.equal((await c.company('123')).id,'urn:li:fsd_company:123');assert.match(path,/companies\/123$/);
 c.api=async()=>({data:{elements:[]}});await assert.rejects(c.company('missing'),e=>e.code==='NOT_FOUND');
});

test('fresh paged caches honor larger limits and refresh replaces membership without losing saved records',async()=>{
 const f=fixture();let calls=0;const factory=()=>({...f.factory(),async search(kind,query,cursor,size){calls++;const start=cursor?.start??0;return{records:Array.from({length:size},(_,i)=>({id:'p'+(start+i),kind:'profile',name:'Person '+(start+i)})),next:{start:start+size},source:'test'};}});
 try{const args=['people','engineer','--page-size','2','--db',f.path];await run([...args,'--limit','1'],{clientFactory:factory,log(){}});const bigger=await run([...args,'--limit','3'],{clientFactory:factory,log(){}});assert.equal(bigger.result.data.length,3);assert.equal(calls,3);}finally{f.clean();}
 const c=new Cache(':memory:');try{c.commit('a','query',[record('old')],null);await sync(c,'a','query',async()=>({records:[record('new')],next:null}),{limit:2});assert.deepEqual(c.list('a',{collection:'query'}).map(r=>r.id),['new']);assert.ok(c.get('a','old'));}finally{c.close();}
});

test('cleanup waits until closed targets stop appearing before allowing the next invocation',async()=>{
 const client=new Client({timeout:1000});let polls=0;const closed=[];client.owned=[{id:'closing',page:{close(){closed.push('page');}}}];client.json=async()=>++polls<3?[{id:'closing'}]:[];client.browser={async call(method){assert.equal(method,'Target.closeTarget');},close(){closed.push('browser');}};await client.close();assert.equal(polls,3);assert.deepEqual(closed,['page','browser']);
});

test('post Markdown uses local wall time across date rollover and DST without the activity-ID note',()=>{
 const previous=process.env.TZ;
 try{for(const [zone,when,date]of [['Asia/Singapore','2026-11-09T20:30:00Z','10 Nov 2026, 04:30 GMT+8'],['America/New_York','2026-07-09T10:30:00Z','9 Jul 2026, 06:30 GMT-4'],['America/New_York','2026-11-09T10:30:00Z','9 Nov 2026, 05:30 GMT-5']]){
 process.env.TZ=zone;const id='urn:li:activity:'+String(BigInt(Date.parse(when))<<22n);const inferred={kind:'post',id,text:'Body'};const published={...inferred,publishedAt:when,publishedAtConfidence:'id'};
 for(const post of [inferred,published,{...published,resharedPost:inferred}]){const output=render({ok:true,data:post},'md',undefined,mdContext('post'));assert.ok(output.includes('Published: '+date),output);assert.doesNotMatch(output,/from activity ID|UTC/);}
 assert.equal(JSON.parse(render({ok:true,data:published},'json')).data.publishedAt,when);
 const partial=render({ok:true,data:{...published,publishedAt:'2026-11-09'}},'md',undefined,mdContext('post'));assert.match(partial,/Published: 9 Nov 2026 ·|Published: 9 Nov 2026\n/);assert.doesNotMatch(partial,/8 Nov/);
 }}finally{if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous;}
});

test('all Markdown time displays use local time while structured timestamps and partial dates retain precision',()=>{
 const previous=process.env.TZ;
 try{for(const [zone,when,expected]of [['Asia/Singapore','2026-11-09T20:30:00Z','10 Nov 2026, 04:30 GMT+8'],['America/New_York','2026-07-09T10:30:00Z','9 Jul 2026, 06:30 GMT-4'],['America/New_York','2026-11-09T02:30:00Z','8 Nov 2026, 21:30 GMT-5']]){
 process.env.TZ=zone;
 const scheduled={kind:'scheduled',scheduledAt:when,text:'Queued content'};
 const analytics={kind:'analytics',postId:mdPost.id,analytics:{scrapedAt:when,reactionCount:1}};
 const samples=[
 ['scheduled',scheduled],['scheduled',[scheduled]],['scheduled',[scheduled,scheduled]],
 ['comments',[{kind:'comment',text:'Comment',publishedAt:when}]],
 ['analytics',analytics],['analytics',[analytics,analytics]],
 ['connections',[{kind:'profile',name:'Ada',connectedAt:when}]],
 ['invitations',[{kind:'invitation',name:'Ada',sentAt:when}]],
 ['cache get',{kind:'invitation',name:'Ada',sentAt:when}],
 ['find',[{kind:'history',name:'Saved',visitedAt:when}]],
 ['cache get',{kind:'history',name:'Saved',visitedAt:when}],
 ['cache get',{kind:'unknown',details:{updated_at:when}}],
 ['cache status',{counts:[],collections:[{key:'saved',updated_at:when}],runs:[{started_at:when}]}],
 ['profile',{kind:'profile',name:'Ada',observedAt:when}],
 ];
 for(const [operation,data]of samples){const result={ok:true,data,meta:{source:'cache',observed_at:when}};
 const output=render(result,'md',undefined,mdContext(operation));assert.ok(output.includes(expected),operation+': '+output);assert.doesNotMatch(output,/UTC|20:30|02:30|10:30/);
 assert.deepEqual(JSON.parse(render(result,'json')),result);assert.deepEqual(JSON.parse(render(result,'ndjson').trim().split('\n')[0]).data,Array.isArray(data)?data[0]:data);
 }
 const notes=render({ok:true,data:{kind:'profile',name:'Ada'},meta:{source:'cache',observed_at:when}},'md',undefined,mdContext('profile'));assert.ok(notes.includes('last fetched '+expected));
 for(const data of [{kind:'profile',observedAt:when},[{kind:'profile',observedAt:when}]]){const selected=render({ok:true,data},'md','observedAt',mdContext('profile'));assert.ok(selected.includes(expected),selected);}
 const partial=render({ok:true,data:[{kind:'profile',name:'Ada',connectedAt:'2026-11-09',sentAt:'2026-11',visitedAt:'August 2026'}]},'md',undefined,mdContext('connections'));assert.match(partial,/9 Nov 2026/);assert.match(partial,/Nov 2026/);assert.match(partial,/August 2026/);assert.doesNotMatch(partial,/GMT|UTC/);
 }}finally{if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous;}
});

test('showcase URLs and typed showcase targets resolve through organization lookup, bypassing member ambiguity',async()=>{
 const {activityTarget,resolveActivityTarget}=await import('../linkedin');assert.deepEqual(activityTarget('https://www.linkedin.com/showcase/claude/posts/?feedView=all'),{company:'claude'});assert.deepEqual(activityTarget('showcase:claude'),{company:'claude'});assert.throws(()=>activityTarget('https://www.linkedin.com/showcase/'));assert.throws(()=>activityTarget('showcase:bad/name'));
 const calls=[],organization={kind:'company',id:'urn:li:fsd_company:106863934',name:'Claude',url:'https://www.linkedin.com/showcase/claude/'};
 for(const value of ['showcase:claude','https://www.linkedin.com/showcase/claude/']){const actor=await resolveActivityTarget(value,{profile(){throw Error('Must not look up person');},async company(slug){calls.push(slug);return organization;}},()=>{throw Error('Must not search');});assert.equal(actor,organization);}assert.deepEqual(calls,['claude','claude']);
 const f=fixture();try{const factory=()=>({...f.factory(),async company(){return organization;},async authorPosts(actors){assert.equal(actors[0].id,organization.id);return{records:[{id:'showcase-post',kind:'post',author:{name:'Claude'},text:'Showcase content',publishedAt:'2026-11-10T00:00:00Z'}],next:null,source:'voyager'};}});
 const args=['activity','showcase:claude','--db',f.path];const live=await run(args,{clientFactory:factory,log(){}});assert.equal(live.result.data[0].author.name,'Claude');const offline=await run([...args,'--offline'],{clientFactory(){throw Error('Must stay offline');}});assert.equal(offline.result.data[0].id,'showcase-post');
 }finally{f.clean();}
});
