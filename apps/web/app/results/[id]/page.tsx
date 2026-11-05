import Link from 'next/link';
import { notFound } from 'next/navigation';
import styles from './page.module.css';
import FollowUpEngine from './FollowUpEngine';

interface Law {
  section: string;
  title: string;
  similarity_score: number;
  explanation: string;
  applies_because: string;
}

function prettyDomain(domain: string): string {
  const [head, ...rest] = domain.split('_');
  const base = head.charAt(0).toUpperCase() + head.slice(1);
  return rest.length ? `${base} (${rest.join(' ')})` : base;
}

function confidenceBand(score: number): { label: string; tone: 'high' | 'medium' | 'low' } {
  if (score >= 0.7) return { label: 'High confidence', tone: 'high' };
  if (score >= 0.45) return { label: 'Medium confidence', tone: 'medium' };
  return { label: 'Low confidence', tone: 'low' };
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <Link href="/" className="wordmark">
          Andha<span>Kaanun</span>
        </Link>
        <Link href="/" className={styles.newLink}>
          New analysis
        </Link>
      </header>
      {children}
    </div>
  );
}

// Next.js 14 Server Component Page
export default async function ResultsPage({ params }: { params: { id: string } }) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

  let data;
  let status = 0;
  try {
    const res = await fetch(`${API_URL}/cases/${params.id}`, {
      // Always fetch fresh: a refinement overwrites the stored analysis.
      next: { revalidate: 0 },
    });
    status = res.status;
    if (res.ok) data = await res.json();
    else if (status !== 404) throw new Error(`Failed to fetch case: ${res.statusText}`);
  } catch (error) {
    console.error(error);
    return (
      <Shell>
        <div className={styles.stateBox}>
          <h1>Could not load this analysis</h1>
          <p>The API did not respond. Make sure the backend is running, then reload this page.</p>
        </div>
      </Shell>
    );
  }

  if (status === 404) notFound();

  const caseData = data.analysis;

  if (!caseData) {
    return (
      <Shell>
        <div className={styles.stateBox}>
          <h1>No analysis for this case yet</h1>
          <p>The analysis is still pending or did not complete. Submit the case again from the start page.</p>
        </div>
      </Shell>
    );
  }

  const score: number = caseData.confidence_score ?? 0;
  const band = confidenceBand(score);
  const domains: string[] = data.jurisdiction?.domain ?? [];
  const laws: Law[] = caseData.laws ?? [];
  const timeline: string[] = caseData.timeline ?? [];

  return (
    <Shell>
      <main className={styles.main}>
        <header className={`${styles.header} reveal`}>
          <h1 className={styles.title}>Case analysis</h1>
          <ul className={styles.meta}>
            {data.location && <li>{data.location}</li>}
            {domains.map((d) => (
              <li key={d}>{prettyDomain(d)}</li>
            ))}
            <li>
              {laws.length} {laws.length === 1 ? 'section' : 'sections'} cited
            </li>
            <li className={`${styles.confidence} ${styles[band.tone]}`}>
              <span className="mono">{Math.round(score * 100)}%</span> {band.label}
            </li>
          </ul>
          {data.input_text && (
            <details className={styles.narrative}>
              <summary>Case narrative as submitted</summary>
              <p>{data.input_text}</p>
            </details>
          )}
        </header>

        <section className={`${styles.summary} reveal`} style={{ '--i': 1 } as React.CSSProperties}>
          <h2 className={styles.h2}>Summary</h2>
          <p className={styles.summaryText}>{caseData.summary}</p>
          {timeline.length > 0 && (
            <ol className={styles.timeline}>
              {timeline.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ol>
          )}
        </section>

        <section className={`${styles.argument} reveal`} style={{ '--i': 2 } as React.CSSProperties}>
          <div className={styles.side}>
            <h2 className={styles.sideTitle}>Prosecution</h2>
            <p className={styles.mainArg}>{caseData.prosecution?.main_argument}</p>
            {caseData.prosecution?.strongest_points?.length > 0 && (
              <>
                <h3 className={styles.h3}>Strongest points</h3>
                <ul className={styles.points}>
                  {caseData.prosecution.strongest_points.map((pt: string, i: number) => (
                    <li key={i}>{pt}</li>
                  ))}
                </ul>
              </>
            )}
            <div className={styles.sideNote}>
              <h3 className={styles.h3}>Burden of proof</h3>
              <p>{caseData.prosecution?.burden_of_proof}</p>
            </div>
          </div>

          <div className={styles.versus} aria-hidden="true">
            <span>v.</span>
          </div>

          <div className={styles.side}>
            <h2 className={styles.sideTitle}>Defense</h2>
            <p className={styles.mainArg}>{caseData.defense?.main_argument}</p>
            {caseData.defense?.counter_points?.length > 0 && (
              <>
                <h3 className={styles.h3}>Counter points</h3>
                <ul className={styles.points}>
                  {caseData.defense.counter_points.map((pt: string, i: number) => (
                    <li key={i}>{pt}</li>
                  ))}
                </ul>
              </>
            )}
            {caseData.defense?.possible_loopholes?.length > 0 && (
              <div className={styles.sideNote}>
                <h3 className={styles.h3}>Possible loopholes</h3>
                <ul className={styles.points}>
                  {caseData.defense.possible_loopholes.map((pt: string, i: number) => (
                    <li key={i}>{pt}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>

        <section className={`${styles.block} reveal`} style={{ '--i': 3 } as React.CSSProperties}>
          <h2 className={styles.h2}>Sections cited</h2>
          <p className={styles.blockLede}>
            Only sections retrieved for this case can be cited. Anything else the model names is removed.
          </p>
          {laws.length > 0 ? (
            <div className={styles.laws}>
              {laws.map((law, i) => (
                <article key={i} className={styles.law}>
                  <div className={styles.lawHead}>
                    <span className={`mono ${styles.lawCode}`}>{law.section}</span>
                    <span className={`mono ${styles.lawScore}`} title="Retrieval similarity score">
                      match {law.similarity_score.toFixed(2)}
                    </span>
                  </div>
                  <h3 className={styles.lawTitle}>{law.title}</h3>
                  <p className={styles.lawText}>{law.explanation}</p>
                  <p className={styles.lawWhy}>
                    <strong>Why it applies.</strong> {law.applies_because}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <p className={styles.empty}>No sections from the index matched this case.</p>
          )}
        </section>

        <section className={`${styles.block} reveal`} style={{ '--i': 4 } as React.CSSProperties}>
          <h2 className={styles.h2}>Possible consequences</h2>
          <dl className={styles.consequences}>
            <div>
              <dt>Criminal</dt>
              <dd>{caseData.consequences?.criminal}</dd>
            </div>
            <div>
              <dt>Civil</dt>
              <dd>{caseData.consequences?.civil}</dd>
            </div>
            <div>
              <dt>Bail</dt>
              <dd>{caseData.consequences?.bail_status}</dd>
            </div>
          </dl>
        </section>

        <FollowUpEngine caseId={params.id} missingInfo={caseData.missing_info} />

        <footer className={styles.disclaimer}>{caseData.disclaimer}</footer>
      </main>
    </Shell>
  );
}
