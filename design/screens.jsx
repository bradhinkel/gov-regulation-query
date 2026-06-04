// Screen components for Federal Regulation Query

// ---------- Masthead ----------
function Masthead({ onAbout, onHome }) {
  return (
    <header className="masthead">
      <div className="brand">
        <div className="brand-seal" onClick={onHome} style={{ cursor: 'pointer' }}>
          <Ico name="seal" />
          <span className="wordmark">Federal <span className="reg">Regulation</span> Query</span>
        </div>
        <div className="coverage"><b>8</b> CFR titles indexed · <b>265,641</b> sections grounded</div>
      </div>
      <nav className="nav">
        <button onClick={onAbout}>About</button>
        <a href="#history">Query history&nbsp;→</a>
      </nav>
    </header>
  );
}

// ---------- prose renderer (plain english + legal) ----------
function CiteRef({ children }) { return <span className="cite-ref">{children}</span>; }

function Block({ b }) {
  if (b.t === 'h2') return <h2 dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === 'h3') return <h3 dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === 'p') return <p className={b.lead ? 'lead' : ''} dangerouslySetInnerHTML={{ __html: b.html }} />;
  if (b.t === 'ul') return (
    <ul>
      {b.items.map((it, i) => (
        <li key={i}>
          <span dangerouslySetInnerHTML={{ __html: it.html }} />
          {it.cite && <> <CiteRef>{it.cite}</CiteRef></>}
        </li>
      ))}
    </ul>
  );
  if (b.t === 'quote') return (
    <div className="verbatim">
      <span className="vq">“{b.text}”</span>
      <div className="vmeta">
        <span className="vtag">Verbatim statute</span>
        <span className="vrule" />
        <span className="vcite">{b.cite}</span>
      </div>
    </div>
  );
  return null;
}

function Prose({ blocks }) {
  return <div className="prose">{blocks.map((b, i) => <Block key={i} b={b} />)}</div>;
}

// ---------- Citations rail ----------
function CitationsRail({ citations, density, asGrid }) {
  // group by title, preserve order of first appearance
  const groups = [];
  const seen = {};
  citations.forEach((c) => {
    if (!seen[c.titleNum]) { seen[c.titleNum] = { name: c.titleName, items: [] }; groups.push(seen[c.titleNum]); }
    seen[c.titleNum].items.push(c);
  });
  return (
    <aside id="citations-rail" className={'rail' + (density === 'compact' ? ' compact' : '')}>
      <div className="rail-head">
        <span className="rail-title">
          <Ico name="shieldcheck" style={{ width: 16, height: 16, color: 'var(--verified)' }} />
          Grounded sections <span className="count">{citations.length}</span>
        </span>
        <a href="#ecfr" style={{ fontSize: 11, color: 'var(--text-3)', display: 'inline-flex', alignItems: 'center', gap: 5 }} title="Open on eCFR.gov">
          eCFR <Ico name="ext" style={{ width: 11, height: 11 }} />
        </a>
      </div>
      <div className="rail-sub">
        Every claim in the answer traces to one of these <b>{citations.length}</b> sections.
      </div>
      <div className="rail-list">
        {groups.map((g, gi) => (
          <React.Fragment key={gi}>
            <div className="title-group-label">{g.name}</div>
            {g.items.map((c) => <CiteCard key={c.n} c={c} />)}
          </React.Fragment>
        ))}
      </div>
    </aside>
  );
}

function CiteCard({ c }) {
  return (
    <button className="cite-card">
      <span className="ext"><Ico name="ext" /></span>
      <div className="cc-top">
        <span className="cite-num">{c.n}</span>
        <div className="cite-main">
          <div className="cite-ref-line">{c.ref}</div>
          <div className="cite-heading">{c.heading}</div>
          <div className="cite-agency"><span className="ag">{c.agency}</span> · {c.dept}</div>
          <div className="cite-fresh"><span className="fdot" />current as of {c.date}</div>
        </div>
      </div>
    </button>
  );
}

// ---------- Result view ----------
function ResultView({ data, t, onNew }) {
  const [reg, setReg] = useState('plain'); // plain | legal
  const conf = data.confidence;
  const stacked = t.registers === 'stacked';

  const confLabel = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' }[conf.tier];

  const flashRail = () => {
    const el = document.getElementById('citations-rail');
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 76;
    window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    el.classList.remove('flash');
    void el.offsetWidth; // restart animation
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 1500);
  };

  return (
    <div className="fade-in">
      {/* compact search bar */}
      <div className="searchbar">
        <Ico name="search" className="icon" style={{ width: 18, height: 18 }} />
        <span className="q-text">{data.query}</span>
        <Field value="All titles" options={['All titles', 'Title 7 — Agriculture', 'Title 21 — Food & Drugs']} />
        <button className="btn-edit" onClick={onNew}>New search</button>
      </div>

      {/* trust bar — the confidence/grounding/freshness trio lives here, up top */}
      <div className="trustbar">
        <h1 className="answer-q">{data.query}</h1>
        <div className="trust-chips">
          <button className="trust-chip grounded" onClick={flashRail}
                  title={`Jump to the ${data.citations.length} cited sections`}>
            <Ico name="shieldcheck" />Grounded in <b>{data.citations.length}</b> cited sections
            <Ico name="chevron" className="jump" />
          </button>
          <span className="trust-chip fresh">
            <span className="dot" />Current as of <b>Apr 2026</b>
          </span>
          <span className={'trust-chip conf-' + conf.tier} title={`Retrieval ${conf.retrieval}% · Citation coverage ${conf.coverage}%`}>
            <Ico name="shield" />{confLabel}{t.showPct ? <> · <b>{conf.score}%</b></> : null}
          </span>
          <button className="btn-print"><Ico name="printer" />Print / PDF</button>
        </div>
      </div>

      {stacked ? (
        <StackedRegisters data={data} t={t} />
      ) : (
        <div className="result-grid">
          <section className="panel">
            <div className="panel-tabbar">
              <div className="seg">
                <button aria-selected={reg === 'plain'} onClick={() => setReg('plain')}>
                  <Ico name="book" className="ico" />Plain English
                </button>
                <button aria-selected={reg === 'legal'} onClick={() => setReg('legal')}>
                  <Ico name="scale" className="ico" />Legal Language
                </button>
              </div>
              <span className="panel-meta">
                <span className="badge">{data.strategy}</span>
                <span>{(data.latencyMs / 1000).toFixed(1)}s</span>
              </span>
            </div>
            <div className="panel-body">
              <Prose blocks={reg === 'plain' ? data.plain : data.legal} />
            </div>
          </section>
          <CitationsRail citations={data.citations} density={t.citationDensity} />
        </div>
      )}

      <Provenance />
    </div>
  );
}

// provenance / legal qualification footer
function Provenance() {
  return (
    <div className="provenance">
      <Ico name="shield" />
      <span>
        Generated by <b>Federal Regulation Query</b> (regs.bradhinkel.com) from the U.S. eCFR ·
        retrieved June 3, 2026. This is informational only and not legal advice — verify against
        the official eCFR at <a href="#ecfr">ecfr.gov</a> before relying on this text.
      </span>
    </div>
  );
}

// stacked = all three registers as sequential sections
function StackedRegisters({ data, t }) {
  return (
    <div className="result-grid stacked">
      <section className="panel">
        <div className="panel-tabbar">
          <div className="seg"><button aria-selected="true"><Ico name="book" className="ico" />Plain English</button></div>
          <span className="panel-meta"><span className="badge">{data.strategy}</span><span>{(data.latencyMs/1000).toFixed(1)}s</span></span>
        </div>
        <div className="panel-body"><Prose blocks={data.plain} /></div>
      </section>
      <section className="panel">
        <div className="panel-tabbar">
          <div className="seg"><button aria-selected="true"><Ico name="scale" className="ico" />Legal Language</button></div>
          <span className="panel-meta">verbatim quotes preserved</span>
        </div>
        <div className="panel-body"><Prose blocks={data.legal} /></div>
      </section>
      <CitationsRail citations={data.citations} density={t.citationDensity} asGrid />
    </div>
  );
}

// ---------- Pipeline loader ----------
function Loader({ data }) {
  const steps = data.pipeline;
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (active >= steps.length) return;
    const dur = Math.max(700, Math.min(1600, steps[active].ms / 3));
    const id = setTimeout(() => setActive((a) => a + 1), dur);
    return () => clearTimeout(id);
  }, [active]);
  return (
    <div className="loader fade-in">
      <div className="loader-head">
        Answering <span className="q">“{data.query}”</span>
      </div>
      <div className="pipeline">
        {steps.map((s, i) => {
          const state = i < active ? 'done' : i === active ? 'active' : 'pending';
          return (
            <div className="pstep" data-state={state} key={i}>
              <span className="pdot">
                {state === 'done' ? <Ico name="check" className="check" />
                  : state === 'active' ? <span className="spin" /> : (i + 1)}
              </span>
              <div>
                <div className="plabel">{s.label}</div>
                <div className="psub">{s.sub}</div>
              </div>
              {state === 'done' && <span className="ptime">{s.ms} ms</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- non-result states ----------
function OffTopic() {
  return (
    <div className="statecard offtopic fade-in">
      <span className="si"><Ico name="alert" style={{ width: 20, height: 20 }} /></span>
      <div>
        <div className="st">Outside the Code of Federal Regulations</div>
        <div className="sd">This system answers questions about U.S. federal regulations only. Try rephrasing as a regulatory question — for example, “What does the FDA require on packaged food labels?”</div>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <div className="statecard notfound fade-in">
      <span className="si"><Ico name="empty" style={{ width: 22, height: 22 }} /></span>
      <div>
        <div className="st">No grounded sections found</div>
        <div className="sd">We searched all 8 indexed titles and found no regulatory text that directly answers this. Rather than guess, the system declines — narrow the scope or try a related term.</div>
      </div>
    </div>
  );
}

// ---------- About modal ----------
function AboutModal({ onClose }) {
  useEffect(() => {
    const k = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, []);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>About this tool</h2>
          <button className="modal-x" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <p className="modal-summary">
            Government Regulation Query is a retrieval-augmented system over the U.S. Code of Federal Regulations.
            Ask a plain-English question and get three grounded answers — a plain-English explanation, a formal
            legal-language synthesis with verbatim quotes, and precise CFR citations — each tied to the current eCFR edition.
          </p>
          <div className="modal-stats">
            <div className="modal-stat"><div className="v">8</div><div className="k">CFR titles indexed</div></div>
            <div className="modal-stat"><div className="v">265K</div><div className="k">sections grounded</div></div>
            <div className="modal-stat"><div className="v">3</div><div className="k">answer registers</div></div>
          </div>
          <div className="modal-links">
            <div className="modal-link"><span className="ml-l">Built by Brad Hinkel</span><span className="ml-r">bradhinkel.com <Ico name="ext" style={{ width: 13, height: 13 }} /></span></div>
            <div className="modal-link"><span className="ml-l">Source on GitHub</span><span className="ml-r">repository <Ico name="ext" style={{ width: 13, height: 13 }} /></span></div>
            <div className="modal-link"><span className="ml-l">Built with Claude Code</span><span className="ml-r">claude.com/claude-code <Ico name="ext" style={{ width: 13, height: 13 }} /></span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Masthead, ResultView, Loader, OffTopic, NotFound, AboutModal, CitationsRail });
