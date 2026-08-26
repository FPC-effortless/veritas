const shell = {
  maxWidth: 1120,
  margin: '0 auto',
  padding: '0 24px',
}

const card = {
  border: '1px solid #e4e4e7',
  borderRadius: 18,
  padding: 24,
  background: '#ffffff',
}

export default function Page() {
  const pilotHref =
    process.env.NEXT_PUBLIC_PILOT_CONTACT ||
    'https://github.com/FPC-effortless/veritas/tree/main/docs/commercial'

  return (
    <main style={{ minHeight: '100vh', background: '#fafafa', color: '#18181b' }}>
      <header style={{ borderBottom: '1px solid #e4e4e7', background: '#ffffff' }}>
        <div
          style={{
            ...shell,
            minHeight: 68,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 24,
          }}
        >
          <strong style={{ fontSize: 18, letterSpacing: '-0.02em' }}>Veritas</strong>
          <a
            href={pilotHref}
            style={{
              color: '#18181b',
              fontSize: 14,
              fontWeight: 650,
              textDecoration: 'none',
              border: '1px solid #d4d4d8',
              borderRadius: 999,
              padding: '10px 16px',
            }}
          >
            Request a design-partner pilot
          </a>
        </div>
      </header>

      <section style={{ ...shell, paddingTop: 96, paddingBottom: 80 }}>
        <p
          style={{
            margin: 0,
            fontSize: 13,
            fontWeight: 700,
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: '#71717a',
          }}
        >
          Enterprise agent evaluation
        </p>
        <h1
          style={{
            maxWidth: 900,
            margin: '20px 0 24px',
            fontSize: 'clamp(44px, 7vw, 76px)',
            lineHeight: 0.98,
            letterSpacing: '-0.055em',
            fontWeight: 760,
          }}
        >
          Find where your AI agent breaks before production does.
        </h1>
        <p
          style={{
            maxWidth: 760,
            margin: 0,
            fontSize: 20,
            lineHeight: 1.55,
            color: '#52525b',
          }}
        >
          Veritas evaluates agents inside a controlled synthetic enterprise with hidden ground truth,
          conflicting operational systems, budgets, authority constraints, and independent verification.
          The result is a capability report you can use to choose models, harnesses, permissions, and
          training priorities.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 34 }}>
          <a
            href={pilotHref}
            style={{
              background: '#18181b',
              color: '#ffffff',
              textDecoration: 'none',
              borderRadius: 999,
              padding: '13px 20px',
              fontWeight: 700,
              fontSize: 15,
            }}
          >
            Request a pilot
          </a>
          <a
            href="https://github.com/FPC-effortless/veritas"
            style={{
              background: '#ffffff',
              color: '#18181b',
              textDecoration: 'none',
              border: '1px solid #d4d4d8',
              borderRadius: 999,
              padding: '13px 20px',
              fontWeight: 650,
              fontSize: 15,
            }}
          >
            Inspect the framework
          </a>
        </div>
      </section>

      <section style={{ ...shell, paddingBottom: 80 }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
            gap: 16,
          }}
        >
          {[
            ['Hidden truth', 'The evaluated agent never receives private evaluator targets, seeds, or ground truth.'],
            ['Operational friction', 'Systems can disagree, evidence can be incomplete, tools have costs, and permissions matter.'],
            ['Independent scoring', 'Outcomes, evidence quality, authority compliance, recovery, and efficiency are verified separately.'],
            ['Reproducible runs', 'Every customer run is versioned with benchmark, model, harness, budget, and run metadata.'],
          ].map(([title, body]) => (
            <article key={title} style={card}>
              <h2 style={{ margin: '0 0 10px', fontSize: 18 }}>{title}</h2>
              <p style={{ margin: 0, color: '#52525b', lineHeight: 1.6, fontSize: 15 }}>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section style={{ background: '#18181b', color: '#ffffff', padding: '80px 0' }}>
        <div style={shell}>
          <p
            style={{
              margin: 0,
              color: '#a1a1aa',
              fontWeight: 700,
              fontSize: 13,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
            }}
          >
            Veritas CompanyWorld Pilot v1
          </p>
          <h2
            style={{
              maxWidth: 780,
              margin: '18px 0 36px',
              fontSize: 'clamp(34px, 5vw, 54px)',
              lineHeight: 1.05,
              letterSpacing: '-0.04em',
            }}
          >
            Turn one deployment question into evidence.
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
              gap: 24,
            }}
          >
            {[
              ['1. Integrate', 'Connect an OpenAI-compatible model endpoint or agreed agent harness.'],
              ['2. Dry run', 'Validate tool schemas, output parsing, budgets, replay, and trajectory capture.'],
              ['3. Private evaluation', 'Run a frozen private suite without exposing hidden task truth.'],
              ['4. Readout', 'Receive a scorecard, failure trajectories, capability gaps, and recommended next experiments.'],
            ].map(([title, body]) => (
              <div key={title}>
                <h3 style={{ margin: '0 0 10px', fontSize: 18 }}>{title}</h3>
                <p style={{ margin: 0, color: '#d4d4d8', lineHeight: 1.65, fontSize: 15 }}>{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={{ ...shell, paddingTop: 80, paddingBottom: 80 }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: 40,
          }}
        >
          <div>
            <h2 style={{ margin: '0 0 16px', fontSize: 32, letterSpacing: '-0.035em' }}>Questions Veritas can answer</h2>
            <p style={{ margin: 0, color: '#52525b', lineHeight: 1.65 }}>
              The pilot is scoped around a decision, not a generic benchmark score.
            </p>
          </div>
          <ul style={{ margin: 0, paddingLeft: 22, color: '#3f3f46', lineHeight: 1.9 }}>
            <li>Which model or harness should we deploy?</li>
            <li>Why does our agent fail on longer operational work?</li>
            <li>Does more inference compute justify its cost?</li>
            <li>Which permissions or tools improve success safely?</li>
            <li>Did a new model, prompt, or training run actually improve capability?</li>
          </ul>
        </div>
      </section>

      <section id="pilot" style={{ ...shell, paddingBottom: 96 }}>
        <div
          style={{
            ...card,
            background: '#f4f4f5',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 24,
            flexWrap: 'wrap',
          }}
        >
          <div>
            <h2 style={{ margin: '0 0 8px', fontSize: 28, letterSpacing: '-0.03em' }}>Design-partner pilots are open.</h2>
            <p style={{ margin: 0, color: '#52525b', lineHeight: 1.6 }}>
              Start with one model or agent, one concrete deployment decision, and a frozen private evaluation.
            </p>
          </div>
          <a
            href={pilotHref}
            style={{
              background: '#18181b',
              color: '#ffffff',
              textDecoration: 'none',
              borderRadius: 999,
              padding: '13px 20px',
              fontWeight: 700,
              fontSize: 15,
              whiteSpace: 'nowrap',
            }}
          >
            Request a pilot
          </a>
        </div>
      </section>

      <footer style={{ borderTop: '1px solid #e4e4e7', background: '#ffffff' }}>
        <div
          style={{
            ...shell,
            paddingTop: 28,
            paddingBottom: 28,
            display: 'flex',
            justifyContent: 'space-between',
            gap: 16,
            flexWrap: 'wrap',
            color: '#71717a',
            fontSize: 13,
          }}
        >
          <span>Veritas · Independent enterprise-agent evaluation</span>
          <span>No production customer data required for the standard synthetic pilot.</span>
        </div>
      </footer>
    </main>
  )
}
