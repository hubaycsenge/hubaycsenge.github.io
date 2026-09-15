// GitHub sign-in in front of the restricted wiki (Cloudflare Pages Functions).
//
// Runs before every request to the Pages project — pages, search index and
// assets alike. A visitor gets through only with a signed session cookie for a
// GitHub login listed in ALLOWED_GITHUB_USERS. Everything else gets a login page
// (401) or a not-authorised page (403). If any setting is missing the site
// fails closed with 503; it never falls back to serving the wiki.
//
// Settings (Pages project secrets, see README.md "The restricted wiki"):
//   GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET   the GitHub OAuth App
//   SESSION_SECRET                           random string that signs cookies
//   ALLOWED_GITHUB_USERS                     GitHub usernames, comma or space separated
//   CANONICAL_HOST (optional)                defaults to csenge-wiki.pages.dev

const SESSION_COOKIE = "wiki_session";
const STATE_COOKIE = "wiki_oauth_state";
const SESSION_TTL = 7 * 24 * 3600; // seconds
const STATE_TTL = 600;
const PUBLIC_SITE = "https://hubaycsenge.github.io";
const REQUIRED = ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "SESSION_SECRET", "ALLOWED_GITHUB_USERS"];

export async function onRequest({ request, env, next }) {
  const url = new URL(request.url);

  const missing = REQUIRED.filter((k) => !env[k]);
  if (missing.length) {
    return page(503, "Not configured", "<p>The wiki's sign-in is not configured yet.</p>");
  }

  // Previews (<hash>.csenge-wiki.pages.dev) carry the same content, but the OAuth
  // callback only works on one host — send everyone there.
  const canonical = env.CANONICAL_HOST || "csenge-wiki.pages.dev";
  if (url.hostname !== canonical) {
    return Response.redirect(`https://${canonical}${url.pathname}${url.search}`, 302);
  }

  const allowed = new Set(
    String(env.ALLOWED_GITHUB_USERS)
      .split(/[\s,]+/)
      .map((u) => u.replace(/^@/, "").toLowerCase())
      .filter(Boolean),
  );

  switch (url.pathname) {
    case "/auth/login":
      return login(url, env);
    case "/auth/callback":
      return callback(request, url, env, allowed);
    case "/auth/logout":
      return page(200, "Signed out", `<p>You are signed out of WikiLLM.</p>${signInButton("/")}`, {
        "Set-Cookie": cookie(SESSION_COOKIE, "", 0, "/"),
      });
  }

  const user = await readSession(request, env);
  if (!user) {
    const target = url.pathname + url.search;
    return page(
      401,
      "Sign in",
      `<p>WikiLLM, the PhD research wiki, is open to invited readers only. Sign in with the
      GitHub account that was given access.</p>${signInButton(target)}`,
    );
  }
  if (!allowed.has(user)) return notAuthorised(user);

  // The deployment holds only the wiki; there is no page at the root.
  if (url.pathname === "/" || url.pathname === "/index.html") {
    return new Response(null, { status: 302, headers: { Location: `/wiki/${url.search}`, "Cache-Control": "no-store" } });
  }

  const response = await next();
  const out = new Response(response.body, response);
  out.headers.set("Cache-Control", "private, no-store");
  out.headers.set("X-Robots-Tag", "noindex, nofollow");
  return out;
}

// --- OAuth flow --------------------------------------------------------------

function login(url, env) {
  const state = randomHex(32);
  const target = safePath(url.searchParams.get("next"));
  const authorize = new URL("https://github.com/login/oauth/authorize");
  authorize.searchParams.set("client_id", env.GITHUB_CLIENT_ID);
  authorize.searchParams.set("redirect_uri", `${url.origin}/auth/callback`);
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("allow_signup", "false");
  // No scope: the public profile (the username) is all that is read.
  return new Response(null, {
    status: 302,
    headers: {
      Location: authorize.toString(),
      "Set-Cookie": cookie(STATE_COOKIE, `${state}|${encodeURIComponent(target)}`, STATE_TTL, "/auth"),
      "Cache-Control": "no-store",
    },
  });
}

async function callback(request, url, env, allowed) {
  const [expected, encodedTarget] = (readCookie(request, STATE_COOKIE) || "").split("|");
  const state = url.searchParams.get("state");
  const code = url.searchParams.get("code");
  const clearState = cookie(STATE_COOKIE, "", 0, "/auth");
  if (!expected || !state || !code || !timingSafeEqual(expected, state)) {
    return page(400, "Sign-in failed", `<p>The sign-in link expired or was not started here.</p>${signInButton("/")}`, {
      "Set-Cookie": clearState,
    });
  }

  const token = await fetch("https://github.com/login/oauth/access_token", {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: env.GITHUB_CLIENT_ID,
      client_secret: env.GITHUB_CLIENT_SECRET,
      code,
      redirect_uri: `${url.origin}/auth/callback`,
    }),
  })
    .then((r) => r.json())
    .catch(() => ({}));
  if (!token.access_token) {
    return page(502, "Sign-in failed", `<p>GitHub did not confirm the sign-in.</p>${signInButton("/")}`, {
      "Set-Cookie": clearState,
    });
  }

  const profile = await fetch("https://api.github.com/user", {
    headers: {
      Authorization: `Bearer ${token.access_token}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "csenge-wiki-auth",
    },
  })
    .then((r) => (r.ok ? r.json() : {}))
    .catch(() => ({}));
  const user = String(profile.login || "").toLowerCase();
  if (!user) {
    return page(502, "Sign-in failed", `<p>Could not read your GitHub username.</p>${signInButton("/")}`, {
      "Set-Cookie": clearState,
    });
  }
  if (!allowed.has(user)) {
    const res = notAuthorised(user);
    res.headers.append("Set-Cookie", clearState);
    return res;
  }

  const headers = new Headers({ Location: safePath(decodeURIComponent(encodedTarget || "")), "Cache-Control": "no-store" });
  headers.append("Set-Cookie", clearState);
  headers.append("Set-Cookie", cookie(SESSION_COOKIE, await signSession(user, env), SESSION_TTL, "/"));
  return new Response(null, { status: 302, headers });
}

// --- sessions ----------------------------------------------------------------

async function signSession(user, env) {
  const payload = b64url(new TextEncoder().encode(JSON.stringify({ u: user, exp: now() + SESSION_TTL })));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(env), new TextEncoder().encode(payload));
  return `${payload}.${b64url(new Uint8Array(sig))}`;
}

async function readSession(request, env) {
  const raw = readCookie(request, SESSION_COOKIE);
  if (!raw || !raw.includes(".")) return null;
  const [payload, sig] = raw.split(".", 2);
  let ok = false;
  try {
    ok = await crypto.subtle.verify("HMAC", await hmacKey(env), unb64url(sig), new TextEncoder().encode(payload));
  } catch {
    return null;
  }
  if (!ok) return null;
  try {
    const data = JSON.parse(new TextDecoder().decode(unb64url(payload)));
    return typeof data.u === "string" && data.exp > now() ? data.u : null;
  } catch {
    return null;
  }
}

function hmacKey(env) {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(env.SESSION_SECRET), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
    "verify",
  ]);
}

// --- helpers -----------------------------------------------------------------

const now = () => Math.floor(Date.now() / 1000);

function randomHex(bytes) {
  return [...crypto.getRandomValues(new Uint8Array(bytes))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function b64url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function unb64url(text) {
  const b64 = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

// Only same-site paths: "/wiki/x.html" yes, "//evil.example" or "https://…" no.
function safePath(path) {
  return typeof path === "string" && path.startsWith("/") && !path.startsWith("//") && !path.includes("\\") ? path : "/";
}

function readCookie(request, name) {
  const header = request.headers.get("Cookie") || "";
  for (const part of header.split(/;\s*/)) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i) === name) return part.slice(i + 1);
  }
  return null;
}

function cookie(name, value, maxAge, path) {
  return `${name}=${value}; Max-Age=${maxAge}; Path=${path}; HttpOnly; Secure; SameSite=Lax`;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function signInButton(target) {
  return `<p><a class="btn" href="/auth/login?next=${encodeURIComponent(safePath(target))}">Sign in with GitHub</a></p>`;
}

function notAuthorised(user) {
  return page(
    403,
    "Not authorised",
    `<p>You are signed in to GitHub as <b>@${escapeHtml(user)}</b>, which is not on the WikiLLM
    reader list.</p>
    <p>To ask for access, write to <a href="mailto:csengehubay@inf.elte.hu?subject=WikiLLM%20access%20request">csengehubay@inf.elte.hu</a>
    with your GitHub username.</p>
    <p class="fine">Wrong account? Sign out of GitHub, then <a href="/auth/login?next=%2F">sign in again</a>.</p>`,
  );
}

// Assets are behind the sign-in too, so these pages carry their own styles.
function page(status, title, body, extraHeaders = {}) {
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${escapeHtml(title)} — WikiLLM</title>
<style>
  :root { --paper:#fbfaf7; --panel:#fff; --ink:#1e1c19; --soft:#55504a; --faint:#837c73; --rule:#cdc7bb; --accent:#1f6f66; --accent-soft:#e4efec; }
  @media (prefers-color-scheme: dark) {
    :root { --paper:#161513; --panel:#1f1d1a; --ink:#ece8e1; --soft:#bdb6ab; --faint:#8f887d; --rule:#3a3631; --accent:#6cc3b7; --accent-soft:#1c2e2b; }
  }
  body { margin:0; padding:0 1rem; background:var(--paper); color:var(--ink);
         font:400 1rem/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; }
  main { max-width:32rem; margin:12vh auto 3rem; padding:2rem 1.8rem; border:1px solid var(--rule); border-radius:12px;
         background:linear-gradient(180deg, var(--accent-soft), var(--panel) 45%); }
  .eyebrow { margin:0; font-size:.72rem; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:var(--accent); }
  h1 { margin:.3rem 0 .8rem; font:600 2rem/1.2 "Iowan Old Style", Palatino, Georgia, serif; }
  p { color:var(--soft); } a { color:var(--accent); } b { color:var(--ink); }
  .btn { display:inline-block; margin-top:.4rem; padding:.8rem 1.4rem; border-radius:7px; background:var(--accent);
         color:var(--paper); font-weight:600; text-decoration:none; }
  .fine { font-size:.85rem; color:var(--faint); }
  .back { margin:1.6rem 0 0; font-size:.88rem; }
</style>
</head>
<body>
<main>
  <p class="eyebrow">🔒 WikiLLM · restricted access</p>
  <h1>${escapeHtml(title)}</h1>
  ${body}
  <p class="back"><a href="${PUBLIC_SITE}/">← Csenge Hubay's homepage</a></p>
</main>
</body>
</html>`;
  return new Response(html, {
    status,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex", ...extraHeaders },
  });
}
