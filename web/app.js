/* ==========================================================================
   Tailscale 控制台 —— 前端逻辑
   数据来源：本机 tailscale 命令行（后端 /api/*），可选叠加管理后台 API
   登录态：校验的是本机 Tailscale 客户端真实登录的账号
   ========================================================================== */

const TOKEN = window.TS_TOKEN;
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let STATE = {
  boot: null,
  meta: null,
  auth: null,
  session: null,
  devices: [],
  filter: 'all',
  keyword: '',
  sort: 'status',
  pingMs: {},
  netcheck: null,
  cloudDevices: [],
  autoTimer: null,
  authPollTimer: null,
  browserFlow: false,
  busy: false,
};

/* ----------------------------- 通用工具 ------------------------------- */

function esc(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function log(title, detail) {
  const box = $('#logBox');
  if (!box) return;
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  box.textContent += `\n[${time}] ${title}${detail ? '\n' + detail : ''}`;
  box.scrollTop = box.scrollHeight;
}

function toast(title, message, kind) {
  const el = document.createElement('div');
  el.className = 'toast' + (kind ? ' ' + kind : '');
  el.innerHTML = `<strong>${esc(title)}</strong>${message ? `<span>${esc(message)}</span>` : ''}`;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), kind === 'bad' ? 9000 : 4200);
}

async function api(path, body) {
  const opt = { method: body === undefined ? 'GET' : 'POST', headers: {} };
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.headers['X-TS-Token'] = TOKEN;
    opt.body = JSON.stringify(body);
  }
  const res = await fetch(path, opt);
  let data = null;
  try { data = await res.json(); } catch (_) { data = null; }
  if (!res.ok) {
    if (data && data.need_login) onSessionLost();
    throw new Error((data && data.err) || `HTTP ${res.status}`);
  }
  return data || {};
}

function busy(on) {
  STATE.busy = on;
  document.body.classList.toggle('loading', on);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制', `${label || ''} ${text}`.trim());
  } catch (_) {
    toast('复制失败', '请手动选中复制', 'bad');
  }
}

/* ----------------------------- 时间/体积格式化 ------------------------ */

function ago(iso) {
  if (!iso) return '未知';
  const t = new Date(iso).getTime();
  if (!t || t < 1000000000000 || String(iso).startsWith('0001')) return '从未在线';
  const diff = Date.now() - t;
  if (diff < 0) return '刚刚';
  const sec = diff / 1000;
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.round(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.round(sec / 3600)} 小时前`;
  const day = Math.round(sec / 86400);
  if (day < 45) return `${day} 天前`;
  const mon = Math.round(day / 30);
  if (mon < 18) return `${mon} 个月前`;
  return `${Math.round(mon / 12)} 年前`;
}

function bytes(num) {
  if (!num) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0, n = num;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}

function dateOnly(iso) {
  if (!iso || String(iso).startsWith('0001')) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return '—';
  return d.toLocaleDateString('zh-CN');
}

/* ----------------------------- 设备归一化 ----------------------------- */

function osKey(os) {
  const s = String(os || '').toLowerCase();
  if (s.includes('windows')) return { cls: 'os-windows', label: 'WIN' };
  if (s.includes('macos') || s.includes('darwin') || s.includes('ios')) {
    return s.includes('ios') ? { cls: 'os-ios', label: 'iOS' } : { cls: 'os-macos', label: 'MAC' };
  }
  if (s.includes('android')) return { cls: 'os-android', label: 'AND' };
  if (s.includes('linux')) return { cls: 'os-linux', label: 'LNX' };
  return { cls: '', label: String(os || '未知').slice(0, 3).toUpperCase() };
}

/* 部分手机端上报的 HostName 是 localhost 之类的通用名，
   这时用 DNS 名的第一段（例如 fanwenlideiphone）更实用。 */
function displayName(raw) {
  const host = String(raw.HostName || '').trim();
  const dnsLabel = raw.DNSName ? String(raw.DNSName).replace(/\.$/, '').split('.')[0] : '';
  const generic = !host || /^(localhost|android|iphone|ipad|desktop|pc|unknown)$/i.test(host);
  return (generic && dnsLabel) ? dnsLabel : (host || dnsLabel || '(无名)');
}

function normalize(status) {
  if (!status) return [];
  const list = [];
  // 注意：登出状态下 status 仍在，但 Self 是个空壳（没有 ID），
  //      直接渲染会多出一张「无地址」的假设备卡。
  const self = status.Self;
  if (self && (self.ID || (self.TailscaleIPs || []).length)) {
    list.push(Object.assign({}, self, { _self: true }));
  }
  Object.values(status.Peer || {}).forEach((p) => list.push(Object.assign({}, p, { _self: false })));
  return list.map((d) => ({
    raw: d,
    self: !!d._self,
    name: displayName(d),
    dns: String(d.DNSName || '').replace(/\.$/, ''),
    os: d.OS || '',
    ips: d.TailscaleIPs || [],
    online: !!d.Online,
    lastSeen: d.LastSeen,
    relay: d.Relay || '',
    direct: !!d.CurAddr,
    curAddr: d.CurAddr || '',
    exitNode: !!d.ExitNode,
    exitOption: !!d.ExitNodeOption,
    sshAllowed: (d.Capabilities || []).some((c) => String(c).includes('cap/ssh')),
    tags: d.Tags || [],
    rx: d.RxBytes || 0,
    tx: d.TxBytes || 0,
    created: d.Created,
    keyExpiry: d.KeyExpiry,
    id: d.ID,
  }));
}

/* ==========================================================================
   登录态
   ========================================================================== */

function avatarFallback(name, login) {
  const raw = String(name || login || '?').trim();
  const initial = (raw.charAt(0) || '?').toUpperCase().replace(/[^0-9A-Za-z\u4e00-\u9fa5]/g, '') || '?';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">`
    + `<rect width="64" height="64" rx="32" fill="#5a4fcf"/>`
    + `<text x="32" y="43" font-size="30" font-family="Segoe UI,sans-serif" font-weight="600"`
    + ` fill="#ffffff" text-anchor="middle">${initial}</text></svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

function applyMeta(meta) {
  if (!meta) return;
  STATE.meta = meta;
  const appVer = 'v' + meta.app.version;
  const cliVer = meta.client.version || '未检测到';
  const download = meta.links.download;

  ['#loginAppVer', '#appVersion', '#footAppVer'].forEach((sel) => {
    const el = $(sel); if (el) el.textContent = appVer;
  });
  ['#loginCliVer', '#footCliVer'].forEach((sel) => {
    const el = $(sel); if (el) el.textContent = cliVer;
  });

  const dl = $('#footDownload');
  if (dl) { dl.dataset.url = download; dl.title = `在浏览器中打开 ${download}`; }
  const ldl = $('#loginDownload');
  if (ldl) ldl.dataset.url = download;
  const bdl = $('#btnDownload');
  if (bdl) bdl.dataset.url = download;
  const ldl2 = $('#linkDownload2');
  if (ldl2) ldl2.dataset.url = download;

  document.title = `Tailscale 控制台 ${appVer}`;
}

function stopAuthPoll() {
  if (STATE.authPollTimer) { clearInterval(STATE.authPollTimer); STATE.authPollTimer = null; }
}

function loginNotice(html, kind) {
  const box = $('#loginNotice');
  if (!html) { box.hidden = true; box.innerHTML = ''; return; }
  box.className = 'login-notice' + (kind ? ' ' + kind : '');
  box.innerHTML = html;
  box.hidden = false;
}

function showLogin(authState, message) {
  stopAuthPoll();
  STATE.auth = authState || STATE.auth || {};
  const ts = STATE.auth.tailscale || {};
  $('#appRoot').hidden = true;
  $('#loginView').hidden = false;

  const accounts = ts.accounts || [];
  let html = '';
  let kind = '';

  if (message) {
    html = `<strong>${esc(message.title)}</strong>${esc(message.body || '')}`;
    kind = message.kind || 'bad';
  } else if (ts.backend_state === 'Stopped') {
    // 守护进程停了，优先提示启动客户端（不管账号是否登录）
    html = `<strong>Tailscale 客户端未运行</strong>守护进程已停止（BackendState=Stopped），设备列表和登录都需要客户端先跑起来。`
      + `<div class="notice-action"><button class="btn btn-sm btn-primary" id="ntStartClient">启动 Tailscale 客户端</button></div>`
      + `<div class="notice-action"><button class="btn btn-sm" id="ntRetry">我已手动启动，刷新状态</button></div>`;
    kind = 'warn';
  } else if (ts.logged_in && accounts.length) {
    const a = accounts[0];
    html = `<strong>本机 Tailscale 已登录</strong>账号 ${esc(a.login)}`
      + `<div class="notice-action"><button class="btn btn-sm btn-primary" id="ntContinue">用这个账号进入</button></div>`;
    kind = 'ok';
  } else if (!ts.ok) {
    html = `<strong>读不到 Tailscale 状态</strong>请确认 Tailscale 客户端已安装并正在运行。`
      + (ts.err ? `<br>${esc(ts.err)}` : '');
    kind = 'bad';
  } else {
    html = `<strong>本机 Tailscale 尚未登录</strong>当前状态：${esc(ts.backend_state || '未知')}。`
      + `先在浏览器完成认证，认证成功后本页会自动进入。`
      + `<div class="notice-action"><button class="btn btn-sm btn-primary" id="ntAuth">打开浏览器认证</button></div>`;
    kind = 'warn';
  }
  loginNotice(html, kind);

  const cont = $('#ntContinue');
  if (cont) cont.onclick = () => doLogin({ method: 'current' });
  const authBtn = $('#ntAuth');
  if (authBtn) authBtn.onclick = () => startBrowserAuth();
  const sc = $('#ntStartClient');
  if (sc) sc.onclick = () => startClient();
  const rt = $('#ntRetry');
  if (rt) rt.onclick = () => { refreshAuthState().then((st) => { if (st) showLogin(st); }); };

  if (ts.logged_in && accounts.length) {
    const a = accounts[0];
    const email = $('#loginEmail');
    if (email && !email.value) email.value = a.login;
  }
}

function showApp() {
  $('#loginView').hidden = true;
  $('#appRoot').hidden = false;
}

function onSessionLost() {
  stopAuthPoll();
  showLogin(null, {
    title: '登录状态已失效',
    body: '本机 Tailscale 账号变了或会话已清除，请重新登录。',
    kind: 'warn',
  });
  refreshAuthState();
}

async function refreshAuthState() {
  try {
    const st = await api('/api/auth/state');
    applyMeta(st.meta);
    STATE.auth = st;
    return st;
  } catch (err) {
    return null;
  }
}

async function doLogin(payload) {
  const btn = $('#loginSubmit');
  const old = btn.textContent;
  btn.disabled = true; btn.textContent = '正在登录…';
  try {
    const res = await api('/api/auth/login', payload);
    if (res.ok) {
      STATE.session = res.session;
      toast('登录成功', res.session.login, 'ok');
      await enterApp();
      return;
    }
    if (res.need_browser_auth) {
      loginNotice(
        `<strong>需要先完成 Tailscale 认证</strong>${esc(res.err || '')}`
        + `<div class="notice-action"><button class="btn btn-sm btn-primary" id="ntAuth">打开浏览器认证</button></div>`,
        'warn');
      const b = $('#ntAuth'); if (b) b.onclick = () => startBrowserAuth();
      return;
    }
    loginNotice(`<strong>登录失败</strong>${esc(res.err || '未知原因')}`
      + (res.hint ? `<div class="notice-action"><button class="btn btn-sm" id="ntUse">改用 ${esc(res.hint)}</button></div>` : ''),
      'bad');
    const u = $('#ntUse');
    if (u) u.onclick = () => { $('#loginEmail').value = res.hint; doLogin({ method: 'email', email: res.hint }); };
  } catch (err) {
    loginNotice(`<strong>登录失败</strong>${esc(err.message)}`, 'bad');
  } finally {
    btn.disabled = false; btn.textContent = old;
  }
}

async function startBrowserAuth() {
  const ts = (STATE.auth && STATE.auth.tailscale) || {};
  const payload = ts.auth_url
    ? { kind: 'auth', url: ts.auth_url }
    : { kind: 'login' };
  try {
    const res = await api('/api/auth/open', payload);
    STATE.browserFlow = true;
    loginNotice(
      `<strong>已在浏览器打开认证页</strong>`
      + `请在浏览器里用 <b>${esc((ts.accounts && ts.accounts[0] && ts.accounts[0].login) || '你的 Tailscale 账号')}</b> 完成登录。`
      + `本页每 3 秒自动检查一次，认证成功后会自动进入。`
      + `<div class="notice-action"><button class="btn btn-sm" id="ntReopen">重新打开认证页</button></div>`,
      'warn');
    const re = $('#ntReopen'); if (re) re.onclick = () => startBrowserAuth();
    startAuthPoll();
  } catch (err) {
    loginNotice(`<strong>打开认证页失败</strong>${esc(err.message)}`, 'bad');
  }
}

async function startClient() {
  const btn = $('#ntStartClient');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    const res = await api('/api/start-client', {});
    if (res && res.ok) {
      loginNotice(`<strong>正在启动 Tailscale 客户端</strong>${esc(res.msg || '')} 等待守护进程就绪...`, 'warn');
      startClientPoll();
    } else {
      loginNotice(`<strong>启动失败</strong>${esc((res && res.err) || '未知原因')}`, 'bad');
      if (btn) { btn.disabled = false; btn.textContent = '启动 Tailscale 客户端'; }
    }
  } catch (e) {
    loginNotice(`<strong>启动失败</strong>${esc(e.message)}`, 'bad');
    if (btn) { btn.disabled = false; btn.textContent = '启动 Tailscale 客户端'; }
  }
}

function startClientPoll() {
  stopAuthPoll();
  let ticks = 0;
  STATE.authPollTimer = setInterval(async () => {
    ticks += 1;
    if (ticks > 60) {  // 最多轮询 2 分钟
      stopAuthPoll();
      loginNotice(`<strong>等待超时</strong>守护进程未在 2 分钟内就绪，请手动打开 Tailscale.app 后点"刷新状态"。`, 'bad');
      return;
    }
    const st = await refreshAuthState();
    if (!st) return;
    const bs = st.tailscale && st.tailscale.backend_state;
    if (bs === 'Running') {
      stopAuthPoll();
      // 客户端起来了，继续走正常登录/进入流程
      if (st.tailscale.logged_in) {
        await doLogin({ method: 'current' });
      } else {
        showLogin(st);
      }
    }
  }, 2000);
}

function startAuthPoll() {
  stopAuthPoll();
  let ticks = 0;
  STATE.authPollTimer = setInterval(async () => {
    ticks += 1;
    if (ticks > 200) { stopAuthPoll(); return; }   // 最多轮询 10 分钟
    const st = await refreshAuthState();
    if (!st) return;
    if (st.logged_in) { stopAuthPoll(); await enterApp(); return; }
    if (st.tailscale && st.tailscale.logged_in) {
      // 浏览器认证完成 -> 本机 tailscaled 已登录，用该账号直接建立会话
      stopAuthPoll();
      await doLogin({ method: 'current' });
    }
  }, 3000);
}

function renderAccount(session) {
  const s = session || {};
  const pic = $('#accountPic');
  pic.onerror = () => { pic.onerror = null; pic.src = avatarFallback(s.name, s.login); };
  pic.src = s.pic || avatarFallback(s.name, s.login);
  $('#accountName').textContent = s.name || s.login || '—';
  $('#accountLogin').textContent = s.login || '—';
  $('#accountChip').title = `当前登录账号：${s.login || '—'}`;
  const foot = $('#footAccount');
  if (foot) foot.textContent = s.login || '—';
  const who = $('#logoutWho');
  if (who) who.textContent = `${s.name || ''} <${s.login || ''}>`.trim();
}

async function enterApp() {
  showApp();
  try {
    const data = await api('/api/bootstrap');
    STATE.boot = data;
    STATE.session = data.session || STATE.session;
    applyMeta(data.meta);
    renderAccount(STATE.session);
    STATE.devices = normalize(data.status);
    renderAll();
    if (data.status_err) {
      toast('读取设备状态失败', data.status_err, 'bad');
      log('bootstrap 异常', data.status_err);
    } else {
      log(`已登录 ${STATE.session ? STATE.session.login : ''}，加载 ${STATE.devices.length} 台设备（客户端 ${data.cli_version || '?'}）`);
    }
  } catch (err) {
    toast('初始化失败', err.message, 'bad');
  }
}

async function doLogout(mode) {
  $('#logoutModal').hidden = true;
  if (mode === 'tailscale') {
    if (!window.confirm('确定要从 Tailscale 登出？\n\n本机会立刻离线，节点密钥作废，必须重新认证才能回到 tailnet。')) return;
    if (!window.confirm('再确认一次：从 Tailscale 登出本机')) return;
  }
  busy(true);
  try {
    const res = await api('/api/auth/logout', { mode });
    log(`$ 注销(${mode})`, res.cmd ? `${res.cmd}\n${res.out || ''}` : (res.out || res.err || ''));
    if (res.ok) toast('已注销', res.out || '', 'ok');
    else toast('注销完成但有异常', res.err || '', 'bad');
    STATE.devices = [];
    STATE.boot = null;
    const st = await refreshAuthState();
    showLogin(st, { title: '已注销', body: `${res.out || ''}`, kind: 'ok' });
  } catch (err) {
    toast('注销失败', err.message, 'bad');
  } finally {
    busy(false);
  }
}

/* ----------------------------- 渲染：设备 ----------------------------- */

function visibleDevices() {
  let list = STATE.devices.slice();
  const kw = STATE.keyword.trim().toLowerCase();

  if (STATE.filter === 'online') list = list.filter((d) => d.online);
  else if (STATE.filter === 'offline') list = list.filter((d) => !d.online);
  else if (STATE.filter === 'exit') list = list.filter((d) => d.exitOption);

  if (kw) {
    list = list.filter((d) =>
      [d.name, d.dns, d.os, d.ips.join(' '), d.relay, (d.tags || []).join(' ')]
        .join(' ').toLowerCase().includes(kw));
  }

  const byName = (a, b) => a.name.localeCompare(b.name, 'zh-CN');
  if (STATE.sort === 'name') list.sort(byName);
  else if (STATE.sort === 'os') list.sort((a, b) => a.os.localeCompare(b.os) || byName(a, b));
  else if (STATE.sort === 'lastseen') list.sort((a, b) => new Date(b.lastSeen || 0) - new Date(a.lastSeen || 0));
  else list.sort((a, b) => (b.self - a.self) || (b.online - a.online) || byName(a, b));

  return list;
}

function renderStats() {
  const all = STATE.devices;
  $('#stTotal').textContent = all.length;
  $('#stOnline').textContent = all.filter((d) => d.online).length;
  $('#stOffline').textContent = all.filter((d) => !d.online).length;
  $('#stExit').textContent = all.filter((d) => d.exitOption).length;
  $('#stDirect').textContent = all.filter((d) => d.direct).length;
}

function renderDevices() {
  const list = visibleDevices();
  const grid = $('#deviceGrid');
  $('#deviceEmpty').hidden = list.length > 0;

  grid.innerHTML = list.map((d) => {
    const osk = osKey(d.os);
    const ping = STATE.pingMs[d.id];
    const chips = [];
    if (d.self) chips.push('<span class="chip chip-accent">本机</span>');
    if (d.exitNode) chips.push('<span class="chip chip-ok">正在用此出口节点</span>');
    else if (d.exitOption) chips.push('<span class="chip chip-accent">出口节点候选</span>');
    if (d.direct) chips.push('<span class="chip chip-ok">直连</span>');
    else if (d.relay) chips.push(`<span class="chip">中继 ${esc(d.relay.toUpperCase())}</span>`);
    if (ping != null) chips.push(`<span class="chip ${ping < 60 ? 'chip-ok' : ping < 150 ? '' : 'chip-warn'}">${ping} ms</span>`);
    if (!d.online) chips.push(`<span class="chip">${esc(ago(d.lastSeen))}</span>`);
    if (d.keyExpiry && !d.self) chips.push(`<span class="chip">密钥 ${esc(dateOnly(d.keyExpiry))} 到期</span>`);
    if (d.rx || d.tx) chips.push(`<span class="chip">↑${esc(bytes(d.tx))} ↓${esc(bytes(d.rx))}</span>`);

    return `
    <article class="dev ${d.self ? 'is-self' : ''} ${d.online ? '' : 'is-offline'}">
      <div class="dev-head">
        <div class="os-badge ${osk.cls}">${esc(osk.label)}</div>
        <div class="dev-title">
          <div class="dev-name">${esc(d.name)}${d.self ? '<span class="tag-self">本机</span>' : ''}</div>
          <div class="dev-dns" title="${esc(d.dns)}">${esc(d.dns || '—')}</div>
        </div>
        <div class="dev-status">
          <span class="dot ${d.online ? 'dot-on' : 'dot-off'}"></span>
          <span class="${d.online ? 'on' : 'off'}">${d.online ? '在线' : '离线'}</span>
        </div>
      </div>

      <div class="dev-ip" data-copy="${esc(d.ips[0] || '')}" title="点击复制 IPv4">
        <span class="ip">${esc(d.ips[0] || '无地址')}</span>
        <span class="copy-tip">点击复制</span>
      </div>

      <div class="dev-meta">${chips.join('')}</div>

      <div class="dev-actions">
        <button class="btn btn-sm" data-act="ping" data-id="${esc(d.id)}" data-target="${esc(d.ips[0] || d.dns)}">Ping</button>
        ${d.self ? '' : `<button class="btn btn-sm" data-act="ssh" data-id="${esc(d.id)}" data-dns="${esc(d.dns)}">SSH 命令</button>`}
        ${d.exitOption && !d.exitNode ? `<button class="btn btn-sm" data-act="exit" data-ip="${esc(d.ips[0])}">设为出口</button>` : ''}
        ${d.exitNode ? '<button class="btn btn-sm" data-act="exit" data-ip="">取消出口</button>' : ''}
        <button class="btn btn-sm" data-act="detail" data-id="${esc(d.id)}">详情</button>
      </div>
    </article>`;
  }).join('');
}

function renderSelfChip() {
  const s = STATE.boot && STATE.boot.status;
  const self = STATE.devices.find((d) => d.self);
  if (!s) {
    $('#selfName').textContent = '未连接';
    $('#selfIP').textContent = '—';
    $('#selfDot').className = 'dot dot-off';
    return;
  }
  const running = s.BackendState === 'Running';
  $('#selfDot').className = 'dot ' + (running ? 'dot-on' : 'dot-off');
  $('#selfName').textContent = (self && self.name) || (s.Self && s.Self.HostName) || '本机';
  $('#selfIP').textContent = (self && self.ips[0]) || '—';
  $('#selfChip').title = `${s.CurrentTailnet ? s.CurrentTailnet.Name : ''}｜TUN ${s.TUN ? '已启用' : '未启用'}`;

  const btn = $('#btnConnect');
  btn.disabled = false;
  btn.textContent = running ? '断开' : '连接';
  btn.className = 'btn ' + (running ? 'btn-danger-ghost' : 'btn-primary');
  btn.dataset.mode = running ? 'disconnect' : 'connect';
}

/* ----------------------------- 渲染：设置 ----------------------------- */

function renderSettings() {
  const s = STATE.boot && STATE.boot.status;
  const p = (STATE.boot && STATE.boot.prefs) || {};
  const self = STATE.devices.find((d) => d.self);
  const meta = STATE.meta || {};

  const selfRows = [
    ['连接状态', s ? (s.BackendState === 'Running' ? '已连接（Running）' : s.BackendState) : '未知'],
    ['登录账号', (STATE.session && STATE.session.login) || '—'],
    ['本机 IPv4', self ? self.ips[0] : '—'],
    ['本机 IPv6', self ? (self.ips[1] || '—') : '—'],
    ['MagicDNS 域名', self ? self.dns : '—'],
    ['网络归属', s && s.CurrentTailnet ? s.CurrentTailnet.Name : '—'],
    ['TUN 虚拟网卡', s ? (s.TUN ? '已启用' : '未启用') : '—'],
    ['出口节点', p.ExitNodeIP ? p.ExitNodeIP : (p.ExitNodeID ? '已设置（ID）' : '未使用')],
    ['子网路由', p.RouteAll ? '接受' : '不接受'],
    ['DNS 配置', p.CorpDNS ? '接受' : '不接受'],
    ['ShieldsUp', p.ShieldsUp ? '已开启' : '关闭'],
    ['管理机构', p.ControlURL || '—'],
  ];
  $('#selfKv').innerHTML = selfRows
    .map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');

  // 软件版本卡片
  $('#verApp').textContent = `Tailscale 控制台 v${(meta.app && meta.app.version) || '—'}`;
  $('#verClient').textContent = (meta.client && meta.client.version) || '未检测到';
  $('#verExe').textContent = (meta.client && meta.client.exe) || '未找到 tailscale.exe';
  $('#verNodeId').textContent = (self && self.raw && self.raw.NodeID) || '—';

  // 开关
  const map = {
    'accept-routes': p.RouteAll,
    'accept-dns': p.CorpDNS,
    'shields-up': p.ShieldsUp,
    'ssh': p.RunSSH,
    'update-check': p.AutoUpdate ? p.AutoUpdate.Check : false,
  };
  if (self && self.raw) map['advertise-exit-node'] = !!self.raw.ExitNodeOption;

  $$('.tgl').forEach((el) => {
    el.checked = !!map[el.dataset.flag];
    el.disabled = false;
  });

  // 出口节点下拉
  const sel = $('#exitSelect');
  const candidates = STATE.devices.filter((d) => d.exitOption && !d.self);
  sel.innerHTML = '<option value="">不使用出口节点（直连上网）</option>' +
    candidates.map((d) =>
      `<option value="${esc(d.ips[0] || d.name)}">${esc(d.name)} · ${esc(d.ips[0] || '')}${d.online ? '（在线）' : '（离线）'}</option>`
    ).join('');
  if (p.ExitNodeIP) sel.value = p.ExitNodeIP;
  $('#exitLanAccess').checked = !!p.ExitNodeAllowLANAccess;
}

/* ----------------------------- 渲染：云端 ----------------------------- */

function renderCloud() {
  const cfg = STATE.boot && STATE.boot.cloud;
  if (cfg) {
    $('#keyStatus').textContent = cfg.has_key
      ? `已配置：${cfg.key_masked}　tailnet：${cfg.tailnet}`
      : '未配置 API Key（只影响本页的远程管理功能）';
    if (!$('#tailnetInput').value && cfg.tailnet && cfg.tailnet !== '-') {
      $('#tailnetInput').value = cfg.tailnet;
    }
  }

  const rows = STATE.cloudDevices;
  $('#cloudCount').textContent = rows.length ? `共 ${rows.length} 台` : '';
  $('#cloudEmpty').hidden = rows.length > 0;

  $('#cloudTable').querySelector('tbody').innerHTML = rows.map((d) => {
    const osk = osKey(d.os);
    const expired = d.keyExpiryDisabled ? '已关闭' : (d.expires ? dateOnly(d.expires) : '—');
    return `<tr>
      <td><strong>${esc(d.name || d.hostname || '')}</strong><br><span class="muted" style="font-size:11px">${esc(d.dnsName || '')}</span></td>
      <td><span class="chip">${esc(osk.label)}</span></td>
      <td class="mono">${esc((d.addresses && d.addresses[0]) || '—')}</td>
      <td>${d.connectedToControl ? '<span class="chip chip-ok">在线</span>' : '<span class="chip">离线</span>'}</td>
      <td>${esc(d.lastSeen ? ago(d.lastSeen) : '—')}</td>
      <td class="mono">${esc(expired)}</td>
      <td>
        <button class="btn btn-sm" data-cact="rename" data-id="${esc(d.id)}" data-name="${esc(d.name || '')}">改名</button>
        <button class="btn btn-sm" data-cact="expire" data-id="${esc(d.id)}" data-name="${esc(d.name || '')}">密钥过期</button>
        <button class="btn btn-sm btn-danger-ghost" data-cact="delete" data-id="${esc(d.id)}" data-name="${esc(d.name || '')}">删除</button>
      </td>
    </tr>`;
  }).join('');
}

/* ----------------------------- 渲染：诊断 ----------------------------- */

function renderNetcheck(result) {
  const rep = result.report || {};
  $('#netcheckSummary').hidden = false;
  $('#netcheckSummary').innerHTML = [
    ['UDP 可用', rep.udp || '—'],
    ['公网 IPv4', rep.ipv4 || '—'],
    ['IPv6', rep.ipv6 || '—'],
    ['NAT 映射随目标变化', rep.mapping_varies || '—'],
    ['最近中继', rep.nearest_derp || '—'],
  ].map(([k, v]) => `<div class="nc-item"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div></div>`).join('');

  const list = rep.derp || [];
  const max = list.length ? Math.max.apply(null, list.map((x) => x.ms)) : 1;
  $('#derpList').innerHTML = list.map((d) =>
    `<div class="derp-row">
       <span class="derp-code">${esc(d.code)}</span>
       <span class="derp-bar"><i style="width:${Math.round((d.ms / max) * 100)}%"></i></span>
       <span class="derp-ms">${d.ms} ms</span>
     </div>`).join('');

  $('#netcheckRawWrap').hidden = false;
  $('#netcheckRaw').textContent = result.out || result.err || '(无输出)';
}

/* ----------------------------- 弹窗 ----------------------------- */

function showDetail(device) {
  const d = device;
  const r = d.raw || {};
  const rows = [
    ['主机名', d.name], ['DNS 名', d.dns], ['操作系统', d.os],
    ['Tailscale IP', d.ips.join(', ')], ['在线', d.online ? '是' : '否'],
    ['最后在线', d.online ? '当前在线' : ago(d.lastSeen)],
    ['最后写入', r.LastWrite && !String(r.LastWrite).startsWith('0001') ? r.LastWrite : '—'],
    ['连接方式', !d.online ? '未连接' : (d.self ? '本机' : (d.direct ? `直连 ${d.curAddr}` : (d.relay ? `经中继 ${d.relay}` : '—')))],
    ['中继区域', d.relay || '—'],
    ['出口节点', d.exitNode ? '本机正通过它上网' : (d.exitOption ? '可作为出口节点' : '否')],
    ['SSH 能力', d.sshAllowed ? '允许' : '未开放'],
    ['Taildrop', r.TaildropTarget ? '可接收文件' : '不可接收'],
    ['接收 / 发送', `${bytes(d.rx)} / ${bytes(d.tx)}`],
    ['加入时间', dateOnly(d.created)],
    ['密钥到期', d.keyExpiry ? dateOnly(d.keyExpiry) : '未设置'],
    ['设备 ID', r.ID || '—'],
    ['NodeID', r.NodeID || '—'],
    ['标签', (d.tags || []).join(', ') || '无'],
  ];
  $('#modalTitle').textContent = `设备详情 · ${d.name}`;
  $('#modalBody').innerHTML =
    `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` +
    `<details class="raw"><summary>完整原始数据</summary><pre>${esc(JSON.stringify(r, null, 2))}</pre></details>` +
    `<div class="row-actions">
       <button class="btn btn-sm" id="mCopyJson">复制原始 JSON</button>
       <button class="btn btn-sm" id="mCopyIp">复制 IP</button>
       <button class="btn btn-sm" id="mCopyDns">复制域名</button>
     </div>`;
  $('#modal').hidden = false;
  $('#mCopyJson').onclick = () => copyText(JSON.stringify(r, null, 2), '设备 JSON');
  $('#mCopyIp').onclick = () => copyText(d.ips[0] || '', 'IP');
  $('#mCopyDns').onclick = () => copyText(d.dns, '域名');
}

/* ----------------------------- 数据加载 ----------------------------- */

async function refresh(quiet) {
  if (STATE.busy || !STATE.boot) return;
  try {
    const data = await api('/api/live');
    if (data.status) {
      STATE.boot.status = data.status;
      STATE.devices = normalize(data.status);
    }
    if (data.prefs) STATE.boot.prefs = data.prefs;
    renderAll();
    if (!quiet) toast('已刷新', `${STATE.devices.length} 台设备`);
  } catch (err) {
    if (!quiet) toast('刷新失败', err.message, 'bad');
  }
}

function renderAll() {
  renderStats();
  renderDevices();
  renderSelfChip();
  renderSettings();
  renderCloud();
}

/* ----------------------------- 动作 ----------------------------- */

async function control(action, extra) {
  busy(true);
  try {
    const res = await api('/api/control', Object.assign({ action }, extra || {}));
    log(`$ ${res.cmd || action}`, (res.out || '') + (res.err ? '\n' + res.err : ''));
    if (res.ok) toast('完成', res.out ? res.out.split('\n')[0] : '操作已执行');
    else toast('失败', res.err || res.out || '未知错误', 'bad');
    await refresh(true);
  } catch (err) {
    toast('失败', err.message, 'bad');
  } finally {
    busy(false);
  }
}

async function doPing(id, target) {
  if (!target) { toast('无法 Ping', '该设备没有可用地址', 'bad'); return; }
  const btn = document.querySelector(`[data-act="ping"][data-id="${id}"]`);
  if (btn) { btn.disabled = true; btn.textContent = 'Ping…'; }
  try {
    const res = await api('/api/ping', { target });
    log(`$ ${res.cmd}`, (res.out || '') + (res.err ? '\n' + res.err : ''));
    const match = (res.out || '').match(/([\d.]+)ms/g);
    if (match && match.length) {
      const ms = Math.round(parseFloat(match[match.length - 1]));
      STATE.pingMs[id] = ms;
      toast('Ping 成功', `${target} → ${res.out.split('\n').pop()}`, 'ok');
    } else {
      toast('Ping 失败', res.err || res.out || '没有收到回应', 'bad');
    }
    renderDevices();
  } catch (err) {
    toast('Ping 失败', err.message, 'bad');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Ping'; }
  }
}

async function doNetcheck() {
  const btn = $('#btnNetcheck');
  btn.disabled = true; btn.textContent = '检测中…';
  try {
    const res = await api('/api/netcheck', {});
    log('$ tailscale netcheck', res.out || res.err);
    renderNetcheck(res);
    toast('检测完成', res.report && res.report.nearest_derp ? `最近中继：${res.report.nearest_derp}` : '');
  } catch (err) {
    toast('检测失败', err.message, 'bad');
  } finally {
    btn.disabled = false; btn.textContent = '开始检测';
  }
}

async function cloudLoad() {
  busy(true);
  try {
    const res = await api('/api/cloud/devices', {});
    if (!res.ok) {
      toast('拉取失败', res.err || '未知错误', 'bad');
      log('管理后台拉取失败', JSON.stringify(res, null, 2));
      return;
    }
    STATE.cloudDevices = (res.data && res.data.devices) || [];
    renderCloud();
    toast('拉取成功', `共 ${STATE.cloudDevices.length} 台设备`);
    log(`管理后台设备：${STATE.cloudDevices.length} 台`);
  } catch (err) {
    toast('拉取失败', err.message, 'bad');
  } finally {
    busy(false);
  }
}

async function cloudOp(op, device) {
  const id = device.id;
  if (op === 'delete') {
    if (!window.confirm(`确定要从 tailnet 中删除「${device.name}」吗？\n\n设备需要重新登录才能回来。此操作不可撤销。`)) return;
    if (!window.confirm(`再次确认：删除「${device.name}」`)) return;
  }
  if (op === 'expire') {
    if (!window.confirm(`让「${device.name}」的密钥立即过期？\n该设备会掉线，需要重新认证后才能回来。`)) return;
  }
  let payload = { op, device_id: id };
  if (op === 'rename') {
    const name = window.prompt('新的设备名：', device.name);
    if (!name) return;
    payload.name = name;
  }
  if (op === 'delete') payload.confirm = id;

  busy(true);
  try {
    const res = await api('/api/cloud/op', payload);
    if (res.ok) { toast('完成', '管理后台已接受操作'); await cloudLoad(); }
    else toast('失败', res.err || '未知错误', 'bad');
  } catch (err) {
    toast('失败', err.message, 'bad');
  } finally {
    busy(false);
  }
}

/* ----------------------------- 事件绑定 ----------------------------- */

function openTailscaleLink(kindOrUrl, isUrl) {
  const payload = isUrl ? { kind: 'auth', url: kindOrUrl } : { kind: kindOrUrl };
  return api('/api/auth/open', payload)
    .catch((err) => toast('打开失败', err.message, 'bad'));
}

function bind() {
  // 登录表单
  $('#loginForm').addEventListener('submit', (e) => {
    e.preventDefault();
    doLogin({ method: 'email', email: $('#loginEmail').value });
  });

  $$('.login-socials .login-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      startBrowserAuth();
    });
  });

  $$('[data-open]').forEach((el) => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      openTailscaleLink(el.dataset.open);
    });
  });

  // 标签页
  $('#tabs').addEventListener('click', (e) => {
    const tab = e.target.closest('.tab');
    if (!tab) return;
    $$('.tab').forEach((t) => t.classList.toggle('is-active', t === tab));
    $$('.panel').forEach((p) => p.classList.toggle('is-active', p.dataset.panel === tab.dataset.tab));
  });

  // 主题
  const saved = localStorage.getItem('ts-theme');
  if (saved) document.documentElement.dataset.theme = saved;
  $('#btnTheme').onclick = () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('ts-theme', next);
  };

  $('#btnRefresh').onclick = () => refresh(false);

  $('#btnConnect').onclick = () => {
    const mode = $('#btnConnect').dataset.mode;
    if (mode === 'disconnect' && !window.confirm('断开本机的 Tailscale 连接？\n断开后本机将无法访问 tailnet 内的设备，随时可以重新连接。')) return;
    control(mode, {});
  };
  $('#btnUp').onclick = () => control('connect', {});
  $('#btnDown').onclick = () => {
    if (!window.confirm('断开本机的 Tailscale 连接？')) return;
    control('disconnect', {});
  };

  // 搜索 / 筛选 / 排序
  $('#searchInput').addEventListener('input', (e) => { STATE.keyword = e.target.value; renderDevices(); });
  $('#filterSeg').addEventListener('click', (e) => {
    const item = e.target.closest('.seg-item');
    if (!item) return;
    STATE.filter = item.dataset.filter;
    $$('.seg-item').forEach((x) => x.classList.toggle('is-active', x === item));
    renderDevices();
  });
  $('#sortSelect').addEventListener('change', (e) => { STATE.sort = e.target.value; renderDevices(); });

  // 自动刷新
  $('#autoRefresh').addEventListener('change', (e) => {
    if (STATE.autoTimer) { clearInterval(STATE.autoTimer); STATE.autoTimer = null; }
    if (e.target.checked) STATE.autoTimer = setInterval(() => refresh(true), 15000);
  });
  STATE.autoTimer = setInterval(() => refresh(true), 15000);

  // 设备卡片操作
  $('#deviceGrid').addEventListener('click', (e) => {
    const ipBox = e.target.closest('.dev-ip');
    if (ipBox && ipBox.dataset.copy) { copyText(ipBox.dataset.copy, 'IPv4'); return; }

    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const device = STATE.devices.find((d) => d.id === btn.dataset.id);
    const act = btn.dataset.act;

    if (act === 'ping') doPing(btn.dataset.id, btn.dataset.target);
    else if (act === 'detail' && device) showDetail(device);
    else if (act === 'ssh') copyText(`ssh ${btn.dataset.dns.replace(/\.$/, '')}`, 'SSH 命令（用户名按需替换）');
    else if (act === 'exit') {
      const ip = btn.dataset.ip;
      if (ip && !window.confirm(`把「${device ? device.name : ip}」设为出口节点？\n本机所有上网流量都会从它出去。`)) return;
      control('set', { flags: [['exit-node', ip || '']] });
    }
  });

  // 开关
  $$('.tgl').forEach((el) => {
    el.addEventListener('change', () => {
      const flag = el.dataset.flag;
      const value = el.checked;
      if (flag === 'advertise-exit-node' && value &&
          !window.confirm('把本机设为出口节点？\n其他设备的上网流量会经过本机，且需要你在管理后台手动批准。')) {
        el.checked = false; return;
      }
      if (flag === 'shields-up' && value) {
        toast('提示', '开启后本机将拒绝所有入站连接，别人无法连你。');
      }
      control('set', { flags: [[flag, value]] });
    });
  });

  // 出口节点
  $('#btnExitApply').onclick = () => {
    const ip = $('#exitSelect').value;
    const pairs = [['exit-node', ip || '']];
    if (ip) pairs.push(['exit-node-allow-lan-access', $('#exitLanAccess').checked]);
    control('set', { flags: pairs });
  };

  // 诊断
  $('#btnNetcheck').onclick = doNetcheck;

  // 云端
  $('#btnSaveKey').onclick = async () => {
    try {
      const res = await api('/api/config', {
        api_key: $('#apiKeyInput').value,
        tailnet: $('#tailnetInput').value,
      });
      STATE.boot.cloud = { has_key: res.has_key, key_masked: res.key_masked, tailnet: res.tailnet };
      $('#apiKeyInput').value = '';
      renderCloud();
      toast('已保存', res.has_key ? `密钥 ${res.key_masked}` : '已清空密钥');
    } catch (err) { toast('保存失败', err.message, 'bad'); }
  };
  $('#btnLoadDevices').onclick = cloudLoad;
  $('#linkKeys').onclick = (e) => {
    e.preventDefault();
    openTailscaleLink('admin');
  };
  $('#cloudTable').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cact]');
    if (!btn) return;
    cloudOp(btn.dataset.cact, { id: btn.dataset.id, name: btn.dataset.name });
  });

  // 版本 / 下载：统一走 tailscale.com/download（后端白名单里固定这个地址）
  ['#footDownload', '#loginDownload', '#btnDownload', '#linkDownload2'].forEach((sel) => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener('click', (e) => {
      e.preventDefault();
      openTailscaleLink('download');
    });
  });

  // 其他
  $('#btnOpenAdmin').onclick = () => openTailscaleLink('admin');
  $('#btnOpenDownload2').onclick = () => openTailscaleLink('console');

  // 注销
  $('#btnLogout').onclick = () => { $('#logoutModal').hidden = false; };
  $('#logoutClose').onclick = () => { $('#logoutModal').hidden = true; };
  $('#logoutModal').addEventListener('click', (e) => {
    if (e.target.id === 'logoutModal') $('#logoutModal').hidden = true;
  });
  $$('#logoutModal .logout-option').forEach((el) => {
    el.addEventListener('click', () => doLogout(el.dataset.mode));
  });

  $('#btnClearLog').onclick = () => { $('#logBox').textContent = ''; };
  $('#modalClose').onclick = () => { $('#modal').hidden = true; };
  $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') $('#modal').hidden = true; });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    $('#modal').hidden = true;
    $('#logoutModal').hidden = true;
  });
}

/* ----------------------------- 启动 ----------------------------- */

async function start() {
  bind();
  const st = await refreshAuthState();
  if (!st) {
    showLogin(null, { title: '无法连接本机服务', body: '请重启控制台程序。', kind: 'bad' });
    return;
  }
  const bs = st.tailscale && st.tailscale.backend_state;
  if (bs === 'Stopped') {
    // 守护进程未运行，无论是否登录都先提示启动客户端
    showLogin(st);
    return;
  }
  if (st.logged_in) {
    STATE.session = st.session;
    await enterApp();
  } else {
    showLogin(st);
  }
}

start();
