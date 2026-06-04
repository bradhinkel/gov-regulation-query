// Home / empty state + App shell

function Home({ onSearch }) {
  const [q, setQ] = useState('');
  const titleOpts = ['All titles', ...window.CFR_TITLES.map((t) => `Title ${t.num} — ${t.name}`)];
  return (
    <div className="fade-in">
      <div className="eyebrow" style={{ marginBottom: 16 }}>
        <span className="tick"><Ico name="shieldcheck" style={{ width: 14, height: 14 }} /></span>
        Retrieval-augmented · grounded in the actual CFR text
      </div>

      <div className="composer">
        <div className="composer-head">
          <textarea
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ask a regulatory question…  e.g. What are the labeling requirements for organic produce? What does 21 CFR require for food additives?"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onSearch(q); }}
          />
        </div>
        <div className="composer-bar">
          <Field label="Filter" value="All titles" options={titleOpts} />
          <Field label="Strategy" value="Sequential (recommended)" options={['Sequential (recommended)', 'Single call']} />
          <span className="spacer" />
          <button className="btn-search" onClick={() => onSearch(q)}>
            <Ico name="search" />Search regulations
          </button>
        </div>
      </div>

      <div className="composer-note">
        <Ico name="shield" />
        Informational only — not legal advice. Every answer is grounded in the current eCFR; verify against the official text at ecfr.gov before relying on it.
      </div>

      <div className="examples">
        <div className="examples-label">Try one of these</div>
        <div className="chip-row">
          {window.EXAMPLES.map((ex, i) => (
            <button className="chip" key={i} onClick={() => onSearch(ex)}>
              <span className="q">?</span>{ex}
            </button>
          ))}
        </div>
      </div>

      <div className="howto">
        <div className="howto-cell">
          <div className="howto-step">STEP 01</div>
          <div className="howto-title">Ask in plain English</div>
          <div className="howto-desc">No legalese required. Filter to a specific CFR title or search all <span className="reg">8 indexed titles</span> at once.</div>
        </div>
        <div className="howto-cell">
          <div className="howto-step">STEP 02</div>
          <div className="howto-title">We retrieve the real text</div>
          <div className="howto-desc">The system pulls grounded sections from the <span className="reg">current eCFR edition</span> — never the model's memory.</div>
        </div>
        <div className="howto-cell">
          <div className="howto-step">STEP 03</div>
          <div className="howto-title">Three grounded answers</div>
          <div className="howto-desc">Every response, verifiable against the source.</div>
          <div className="register-pills">
            <span className="register-pill">Plain English</span>
            <span className="register-pill">Legal Language</span>
            <span className="register-pill">CFR Citations</span>
          </div>
        </div>
      </div>

      <div className="titles-strip">
        <div className="examples-label">Coverage — 8 major titles</div>
        <div className="title-tags">
          {window.CFR_TITLES.map((t) => (
            <span className="title-tag" key={t.num}><span className="num">{t.num}</span>{t.name}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------- App ----------------
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "#5183ff",
  "theme": "dark",
  "headlineSerif": true,
  "registers": "rail",
  "citationDensity": "compact",
  "showPct": false,
  "demoState": "home"
}/*EDITMODE-END*/;

const ACCENTS = {
  "#5183ff": { dim: "rgba(81,131,255,0.14)", line: "rgba(81,131,255,0.4)", two: "#6f9bff" },   // federal blue
  "#3f6ddb": { dim: "rgba(63,109,219,0.14)", line: "rgba(63,109,219,0.4)", two: "#5f88ec" },   // navy
  "#2f9c7a": { dim: "rgba(47,156,122,0.15)", line: "rgba(47,156,122,0.42)", two: "#46b893" },  // federal green
  "#b07d3a": { dim: "rgba(176,125,58,0.15)", line: "rgba(176,125,58,0.42)", two: "#c79653" },  // bronze
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [screen, setScreen] = useState(t.demoState || 'home'); // home | loading | result | offtopic | notfound
  const [about, setAbout] = useState(false);

  // apply theme + accent tokens to :root
  useEffect(() => {
    const r = document.documentElement;
    r.setAttribute('data-theme', t.theme);
    const a = ACCENTS[t.accent] || ACCENTS["#5183ff"];
    r.style.setProperty('--accent', t.accent);
    r.style.setProperty('--accent-2', a.two);
    r.style.setProperty('--accent-dim', a.dim);
    r.style.setProperty('--accent-line', a.line);
    r.style.setProperty('--font-serif', t.headlineSerif ? "'Spectral', Georgia, serif" : "'Public Sans', system-ui, sans-serif");
  }, [t.theme, t.accent, t.headlineSerif]);

  // the "Preview state" selector drives the screen directly
  useEffect(() => { if (t.demoState && t.demoState !== screen) setScreen(t.demoState); }, [t.demoState]);

  const runSearch = () => setScreen('loading');
  useEffect(() => {
    if (screen === 'loading') {
      const total = window.DEMO.pipeline.reduce((s, p) => s + Math.max(700, Math.min(1600, p.ms / 3)), 0) + 300;
      const id = setTimeout(() => setScreen('result'), total);
      return () => clearTimeout(id);
    }
  }, [screen]);

  const goHome = () => { setScreen('home'); setTweak('demoState', 'home'); };
  const setPreview = (v) => { setTweak('demoState', v); setScreen(v); };

  let body;
  if (screen === 'loading') body = <Loader data={window.DEMO} />;
  else if (screen === 'result') body = <ResultView data={window.DEMO} t={t} onNew={goHome} />;
  else if (screen === 'offtopic') body = <><CompactQ /><OffTopic /></>;
  else if (screen === 'notfound') body = <><CompactQ /><NotFound /></>;
  else body = <Home onSearch={runSearch} />;

  return (
    <div className="shell">
      <Masthead onAbout={() => setAbout(true)} onHome={goHome} />
      {body}
      {about && <AboutModal onClose={() => setAbout(false)} />}

      <TweaksPanel title="Tweaks">
        <TweakSection label="Theme" />
        <TweakRadio label="Mode" value={t.theme} options={['dark', 'light']} onChange={(v) => setTweak('theme', v)} />
        <TweakColor label="Accent" value={t.accent}
          options={["#5183ff", "#3f6ddb", "#2f9c7a", "#b07d3a"]}
          onChange={(v) => setTweak('accent', v)} />
        <TweakToggle label="Serif headlines" value={t.headlineSerif} onChange={(v) => setTweak('headlineSerif', v)} />

        <TweakSection label="Answer layout" />
        <TweakRadio label="Registers" value={t.registers} options={[{ value: 'rail', label: 'Tabs + rail' }, { value: 'stacked', label: 'Stacked' }]} onChange={(v) => setTweak('registers', v)} />
        <TweakRadio label="Citations" value={t.citationDensity} options={[{ value: 'comfortable', label: 'Comfortable' }, { value: 'compact', label: 'Compact' }]} onChange={(v) => setTweak('citationDensity', v)} />
        <TweakToggle label="Show confidence %" value={t.showPct} onChange={(v) => setTweak('showPct', v)} />

        <TweakSection label="Preview screen" />
        <TweakSelect label="Show" value={screen}
          options={[
            { value: 'home', label: 'Home / empty state' },
            { value: 'result', label: 'Answer (3 registers)' },
            { value: 'loading', label: 'Pipeline loading' },
            { value: 'offtopic', label: 'Off-topic notice' },
            { value: 'notfound', label: 'Not found' },
          ]}
          onChange={setPreview} />
      </TweaksPanel>
    </div>
  );
}

// little echoed-question bar used above off-topic/not-found previews
function CompactQ() {
  return (
    <div className="searchbar" style={{ marginBottom: 22 }}>
      <Ico name="search" className="icon" style={{ width: 18, height: 18 }} />
      <span className="q-text" style={{ color: 'var(--text-3)' }}>What's the best restaurant in Seattle?</span>
      <button className="btn-edit">New search</button>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
