// Flood Claim Truth-Check Agent — frontend logic

// ---------- theme toggle ----------
const themeToggle = document.getElementById('theme-toggle');
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  themeToggle.setAttribute('aria-pressed', String(theme === 'light'));
  themeToggle.setAttribute('aria-label', theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme');
}
themeToggle.addEventListener('click', () => {
  const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  localStorage.setItem('theme', next);
  applyTheme(next);
});
applyTheme(document.documentElement.getAttribute('data-theme') || 'dark');

// ---------- mobile menu ----------
const menuBtn = document.getElementById('menu-btn');
const mobileMenu = document.getElementById('mobile-menu');
menuBtn.addEventListener('click', () => {
  const open = menuBtn.getAttribute('aria-expanded') === 'true';
  menuBtn.setAttribute('aria-expanded', String(!open));
  mobileMenu.classList.toggle('open', !open);
});
mobileMenu.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
  menuBtn.setAttribute('aria-expanded', 'false');
  mobileMenu.classList.remove('open');
}));

// ---------- scroll reveal ----------
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('in');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.15 });
document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// ---------- tagline word-by-word reveal ----------
const taglineText = "Most flood claims cannot be checked against the document built to verify them. We check them against the ground instead, and cite every fact we use.";
const taglineEl = document.getElementById('tagline');
taglineText.split(' ').forEach((w, i) => {
  const span = document.createElement('span');
  span.className = 'word';
  span.textContent = w;
  span.style.transitionDelay = `${(i % 14) * 40}ms`;
  taglineEl.appendChild(span);
  taglineEl.appendChild(document.createTextNode(' '));
});
const wordObserver = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('in');
      wordObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.6 });
taglineEl.querySelectorAll('.word').forEach(w => wordObserver.observe(w));

// ---------- proof stat ----------
fetch('/api/stats').then(r => r.json()).then(s => {
  document.getElementById('proof-pct').textContent = `${s.missing_cert_pct}%`;
  document.getElementById('proof-frac').textContent =
    `${s.missing_cert_count.toLocaleString()} of ${s.recent_claims_count.toLocaleString()}`;
}).catch(() => {});

// ---------- FAQ ----------
const FAQS = [
  {
    q: "Why is the claim location only approximate?",
    a: "FEMA's public NFIP claims data rounds every location to the nearest 0.1 degree of latitude and longitude, about a seven mile box, to protect the privacy of who filed the claim. This agent checks the physical plausibility of a claim's area, not one exact house. In production, an insurer would run the same logic against their own exact policy addresses, which they already have.",
  },
  {
    q: "Why doesn't a flood zone remap alone count as a red flag?",
    a: "NFIP has an official grandfathering rule that lets a policyholder keep their old flood zone rating even after FEMA remaps the area, specifically so they are not hit with a sudden rate increase. A mismatch between a claim's rated zone and the current zone is usually the program working as intended, not an error, so it is not used as a signal here.",
  },
  {
    q: "What counts as a contradiction?",
    a: "A claim's stated flood risk (its rated zone) disagreeing with Mireye's independently sourced terrain facts for that area: whether the point sits in a mapped floodplain today, nearby wetlands, distance to the coast, and ground elevation.",
  },
  {
    q: "Why require two or more signals instead of one?",
    a: "A single mismatched signal is too easily explained by the seven mile location rounding alone. Requiring at least two independent signals to agree cuts false positives from location fuzziness and keeps the flagged list to genuinely surprising cases.",
  },
  {
    q: "Is a flagged claim proof of fraud or an error?",
    a: "No. A flagged claim is a lead worth a person looking at, not a verdict. The goal is to turn a pile of unverifiable claims into a short, reasoned list for a human reviewer, with every fact cited back to its source.",
  },
  {
    q: "Who would actually use this?",
    a: "FEMA and FIMA, the NFIP's own administrator, whose 2020 Inspector General report already flagged missing elevation certificates and an inability to resolve claim discrepancies. Also the roughly 50 private Write Your Own insurers who administer NFIP policies and are audited for exactly this kind of improper payment.",
  },
  {
    q: "What data sources back this?",
    a: "FEMA's public OpenFEMA NFIP Redacted Claims dataset for the claims themselves, and Mireye's flood_risk preset for terrain, floodplain, wetland, and coastal facts, each sourced to USGS, FEMA NFHL, USFWS, or NOAA with a fetch timestamp.",
  },
  {
    q: "How current is the 91 percent missing certificate figure?",
    a: "It is not from an old report. It comes from live querying FEMA's current OpenFEMA API for claims from 2023 onward, counted directly, each time this page loads its proof stat.",
  },
];

const faqList = document.getElementById('faq-list');
FAQS.forEach(({ q, a }) => {
  const details = document.createElement('details');
  details.className = 'rounded-2xl border border-line bg-panel px-5 py-4 group';
  details.innerHTML = `
    <summary class="cursor-pointer font-semibold flex items-center justify-between gap-4 list-none">
      <span>${q}</span>
      <i class="ph ph-plus text-accent shrink-0 fluid group-open:rotate-45"></i>
    </summary>
    <p class="text-sm text-muted mt-3">${a}</p>
  `;
  faqList.appendChild(details);
});

// ---------- run panel ----------
const runForm = document.getElementById('run-form');
const runBtn = document.getElementById('run-btn');
const runOutput = document.getElementById('run-output');
const runHistory = document.getElementById('run-history');

function fmtMoney(n) {
  return `$${Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
function fmtTime(ts) {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString();
}

function renderLoading(log) {
  runOutput.innerHTML = `
    <div class="rounded-2xl border border-line bg-panel p-5">
      <div class="flex items-center gap-2 mb-4 text-sm text-muted">
        <i class="ph ph-circle-notch animate-spin text-accent"></i> Running…
      </div>
      <div class="space-y-2 font-mono text-xs text-muted mb-4" id="run-log">
        ${log.map(l => `<div>› ${l}</div>`).join('')}
      </div>
      <div class="space-y-3">
        <div class="h-16 rounded-xl skeleton"></div>
        <div class="h-16 rounded-xl skeleton"></div>
        <div class="h-16 rounded-xl skeleton"></div>
      </div>
    </div>
  `;
}

function renderError(message, creditsExhausted) {
  if (creditsExhausted) {
    setCreditsExhausted();
    runOutput.innerHTML = `
      <div class="rounded-2xl border border-red-500 bg-red-500/10 p-5">
        <p class="text-sm text-red-400 flex items-center gap-2 font-semibold"><i class="ph ph-warning-octagon"></i> Mireye API credits have been exhausted.</p>
        <p class="text-sm text-red-400/80 mt-1">This run couldn't finish. It'll pick back up once credits are available again.</p>
      </div>
    `;
    return;
  }
  runOutput.innerHTML = `
    <div class="rounded-2xl border border-line bg-panel p-5">
      <p class="text-sm text-warn flex items-center gap-2"><i class="ph ph-warning"></i> ${message}</p>
    </div>
  `;
}

function setCreditsExhausted() {
  const el = document.getElementById('credits-warning');
  if (!el) return;
  el.classList.remove('text-muted');
  el.classList.add('text-red-400', 'font-semibold');
  el.innerHTML = `
    <i class="ph ph-warning-octagon shrink-0 mt-0.5"></i>
    <span>Mireye API credits have been exhausted. Runs will fail or return partial results until credits are added.</span>
  `;
}

function claimCard(s, claim) {
  const lat = claim ? claim.latitude : '—';
  const lng = claim ? claim.longitude : '—';
  const state = claim ? claim.state : '';
  const date = claim && claim.dateOfLoss ? claim.dateOfLoss.slice(0, 10) : '—';
  const event = (claim && claim.floodEvent) || 'unspecified event';

  const reasons = s.reasons.map(r => `<li class="flex gap-2"><i class="ph ph-warning-circle text-warn shrink-0 mt-0.5"></i><span>${r}</span></li>`).join('');
  const citations = s.citations.map(c => `
    <div class="flex flex-wrap items-center gap-2 text-xs text-muted font-mono">
      <span class="rounded-md bg-panel3 px-2 py-1">${c.field} = ${c.value}</span>
      <span>${c.source}</span>
      <span>${c.confidence} confidence</span>
      <a class="text-accent hover:underline" href="${c.source_url}" target="_blank" rel="noopener">source</a>
    </div>
  `).join('');

  const div = document.createElement('div');
  div.className = 'rounded-2xl border border-line bg-panel p-5';
  div.innerHTML = `
    <div class="flex items-start justify-between gap-4 mb-3">
      <div>
        <p class="text-xs text-muted font-mono">claim ${s.claim_id.slice(0, 8)}</p>
        <p class="text-sm mt-1">${lat}, ${lng} (${state}) — ${date} — ${event}</p>
      </div>
      <span class="rounded-full bg-warn/15 text-warn text-xs font-semibold px-2 py-1 shrink-0">priority ${s.priority}</span>
    </div>
    <div class="flex flex-wrap gap-3 text-xs text-muted mb-3">
      <span>zone <span class="font-mono text-white">${s.claim_zone}</span></span>
      <span>payout <span class="font-mono text-white">${fmtMoney(s.payout)}</span></span>
      <span>score <span class="font-mono text-white">${s.score}</span></span>
    </div>
    <ul class="text-sm space-y-1.5 mb-3">${reasons}</ul>
    <details class="fluid">
      <summary class="cursor-pointer text-xs text-accent">Show Mireye citations</summary>
      <div class="mt-2 space-y-1.5">${citations}</div>
    </details>
  `;
  return div;
}

function renderResults(job) {
  const claims = job.claims_by_id || {};
  const scored = job.scored_claims || [];

  const summary = document.createElement('div');
  summary.className = 'grid grid-cols-2 md:grid-cols-4 gap-3';
  const stats = [
    ['scanned', job.total_scanned],
    ['unique locations', job.unique_locations],
    ['flagged', job.flagged_count],
    ['elapsed', `${job.elapsed_seconds}s`],
  ];
  summary.innerHTML = stats.map(([label, val]) => `
    <div class="rounded-2xl border border-line bg-panel p-4 text-center">
      <p class="font-mono text-xl">${val}</p>
      <p class="text-xs text-muted mt-1">${label}</p>
    </div>
  `).join('');

  runOutput.innerHTML = '';

  if (job.credits_exhausted) {
    setCreditsExhausted();
    const banner = document.createElement('div');
    banner.className = 'rounded-2xl border border-red-500 bg-red-500/10 p-4';
    banner.innerHTML = `
      <p class="text-sm text-red-400 flex items-center gap-2 font-semibold"><i class="ph ph-warning-octagon"></i> Mireye API credits ran out partway through this run.</p>
      <p class="text-sm text-red-400/80 mt-1">These results only cover what was fetched before that happened.</p>
    `;
    runOutput.appendChild(banner);
  }

  runOutput.appendChild(summary);

  if (scored.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'rounded-2xl border border-line bg-panel p-8 text-center text-muted text-sm';
    empty.textContent = 'No contradictions found in this batch. Try a larger sample size.';
    runOutput.appendChild(empty);
    return;
  }

  const list = document.createElement('div');
  list.className = 'space-y-3';
  scored.slice(0, 30).forEach(s => list.appendChild(claimCard(s, claims[s.claim_id])));
  runOutput.appendChild(list);
}

let pollTimer = null;
const runBtnDefaultHTML = runBtn.innerHTML;

function setRunButtonBusy(busy) {
  runBtn.disabled = busy;
  runBtn.classList.toggle('opacity-50', busy);
  runBtn.classList.toggle('cursor-not-allowed', busy);
  runBtn.innerHTML = busy
    ? '<i class="ph ph-circle-notch animate-spin"></i> Running…'
    : runBtnDefaultHTML;
}

function pollRun(runId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const res = await fetch(`/api/runs/${runId}`);
    const job = await res.json();
    if (job.status === 'running') {
      renderLoading(job.log || []);
    } else if (job.status === 'done') {
      clearInterval(pollTimer);
      renderResults(job);
      loadHistory();
      setRunButtonBusy(false);
    } else if (job.status === 'error') {
      clearInterval(pollTimer);
      renderError(job.error || 'The run failed.', job.credits_exhausted);
      setRunButtonBusy(false);
    }
  }, 1000);
}

runForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  setRunButtonBusy(true);
  const year_from = Number(document.getElementById('year-from').value);
  const limit = Number(document.getElementById('limit').value);
  renderLoading(['Starting run…']);
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ year_from, limit }),
  });
  if (!res.ok) {
    renderError('Could not start the run.');
    setRunButtonBusy(false);
    return;
  }
  const { run_id } = await res.json();
  pollRun(run_id);
});

async function loadHistory() {
  const res = await fetch('/api/runs');
  const runs = await res.json();
  if (runs.length === 0) {
    runHistory.innerHTML = '<p class="text-muted text-sm">No runs yet.</p>';
    return;
  }
  runHistory.innerHTML = '';
  runs.slice(0, 12).forEach(r => {
    const btn = document.createElement('button');
    btn.className = 'w-full text-left rounded-lg border border-line bg-panel2 px-3 py-2 hover:border-accent fluid';
    const statusIcon = r.credits_exhausted ? 'ph-warning-octagon text-red-400'
      : r.status === 'done' ? 'ph-check-circle text-accent'
      : r.status === 'error' ? 'ph-x-circle text-warn'
      : 'ph-circle-notch animate-spin text-muted';
    btn.innerHTML = `
      <div class="flex items-center justify-between gap-2">
        <span class="font-mono text-xs">${r.id}</span>
        <i class="ph ${statusIcon}"></i>
      </div>
      <p class="text-xs text-muted mt-1">${r.params.limit} claims since ${r.params.year_from} — ${fmtTime(r.started_at)}</p>
      ${r.status === 'done' ? `<p class="text-xs text-muted">${r.flagged_count} of ${r.total_scanned} flagged</p>` : ''}
    `;
    btn.addEventListener('click', async () => {
      const res = await fetch(`/api/runs/${r.id}`);
      const job = await res.json();
      if (job.status === 'done') { setRunButtonBusy(false); renderResults(job); }
      else if (job.status === 'running') { setRunButtonBusy(true); renderLoading(job.log || []); pollRun(r.id); }
      else { setRunButtonBusy(false); renderError(job.error || 'This run failed.', job.credits_exhausted); }
    });
    runHistory.appendChild(btn);
  });
}

loadHistory();
