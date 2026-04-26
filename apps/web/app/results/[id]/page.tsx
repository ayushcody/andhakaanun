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

// Next.js 14 Server Component Page
export default async function ResultsPage({ params }: { params: { id: string } }) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  
  try {
    const res = await fetch(`${API_URL}/cases/${params.id}`, {
      // Don't strongly cache since we might get a partial response or streaming might just have finished
      next: { revalidate: 0 } 
    });
    
    if (!res.ok) {
      if (res.status === 404) notFound();
      throw new Error(`Failed to fetch case: ${res.statusText}`);
    }
    
    const data = await res.json();
    const caseData = data.analysis;
    
    // If somehow analysis is empty or streaming failed, show minimal state
    if (!caseData) {
      return (
        <div className={styles.container}>
          <h1>Analysis Pending or Failed</h1>
          <p>Please try submitting your case again.</p>
          <Link href="/" className={styles.backBtn}>← Back to Input</Link>
        </div>
      );
    }

    const confidenceClass = caseData.confidence_score > 0.6 ? '' : styles.low;
    const confidenceText = caseData.confidence_score > 0.6 
      ? `${Math.round(caseData.confidence_score * 100)}% Confidence` 
      : 'Low Confidence (Fallback)';

    return (
      <div className={styles.container}>
        <Link href="/" className={styles.backBtn}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          New Analysis
        </Link>
        
        <header className={`${styles.header} animate-fade-in`}>
          <div className={styles.titleWrapper}>
            <h1 className={styles.title}>Legal Analysis Result</h1>
            <div className={`${styles.confidenceBadge} ${confidenceClass}`}>
              {confidenceText}
            </div>
          </div>
        </header>

        {/* Summary Section */}
        <section className={`${styles.section} animate-slide-up`}>
          <h2 className={styles.sectionTitle}>Case Summary</h2>
          <div className={`glass-panel ${styles.contentBox}`}>
            <p className={styles.summaryText}>{caseData.summary}</p>
          </div>
        </section>

        {/* Laws Section */}
        <section className={`${styles.section} animate-slide-up delay-1`}>
          <h2 className={styles.sectionTitle}>Applicable Laws</h2>
          {caseData.laws && caseData.laws.length > 0 ? (
            caseData.laws.map((law: Law, i: number) => (
              <div key={i} className={styles.lawCard}>
                <div className={styles.lawHeader}>
                  <div>
                    <div className={styles.lawSection}>{law.section}</div>
                    <div className={styles.lawTitle}>{law.title}</div>
                  </div>
                  <div className={styles.lawScore}>
                    Match: {Math.round(law.similarity_score * 100)}%
                  </div>
                </div>
                <div className={styles.lawExplanation}>{law.explanation}</div>
                <div className={styles.lawReasoning}>
                  <strong>Why it applies:</strong> {law.applies_because}
                </div>
              </div>
            ))
          ) : (
            <div className="glass-panel" style={{ padding: '1.5rem', color: 'var(--text-muted)' }}>
              No specific laws were identified for this case.
            </div>
          )}
        </section>

        {/* Perspectives Section */}
        <section className={`${styles.section} ${styles.grid} animate-slide-up delay-2`}>
          {/* Prosecution */}
          <div className={`glass-panel ${styles.contentBox} ${styles.perspectiveCard} ${styles.prosecution}`}>
            <h3 className={styles.perspectiveTitle}>Prosecution Perspective</h3>
            <p>{caseData.prosecution?.main_argument}</p>
            <ul className={styles.pointsList}>
              {caseData.prosecution?.strongest_points?.map((pt: string, i: number) => (
                <li key={i}>{pt}</li>
              ))}
            </ul>
            <div style={{ marginTop: '1rem', fontSize: '0.85rem' }}>
              <strong>Burden of Proof:</strong> {caseData.prosecution?.burden_of_proof}
            </div>
          </div>

          {/* Defense */}
          <div className={`glass-panel ${styles.contentBox} ${styles.perspectiveCard} ${styles.defense}`}>
            <h3 className={styles.perspectiveTitle}>Defense Perspective</h3>
            <p>{caseData.defense?.main_argument}</p>
            <ul className={styles.pointsList}>
              {caseData.defense?.counter_points?.map((pt: string, i: number) => (
                <li key={i}>{pt}</li>
              ))}
            </ul>
            {caseData.defense?.possible_loopholes?.length > 0 && (
              <div style={{ marginTop: '1rem', fontSize: '0.85rem' }}>
                <strong>Loopholes:</strong> {caseData.defense?.possible_loopholes.join(', ')}
              </div>
            )}
          </div>
        </section>

        {/* Consequences Section */}
        <section className={`${styles.section} animate-slide-up delay-3`}>
          <h2 className={styles.sectionTitle}>Potential Consequences</h2>
          <div className={`glass-panel ${styles.contentBox} ${styles.consequencesList}`}>
            <div className={styles.consequenceItem}>
              <div className={styles.cLabel}>Criminal</div>
              <div className={styles.cValue}>{caseData.consequences?.criminal}</div>
            </div>
            <div className={styles.consequenceItem}>
              <div className={styles.cLabel}>Civil</div>
              <div className={styles.cValue}>{caseData.consequences?.civil}</div>
            </div>
            <div className={styles.consequenceItem}>
              <div className={styles.cLabel}>Bail Status</div>
              <div className={styles.cValue}>{caseData.consequences?.bail_status}</div>
            </div>
          </div>
        </section>

        {/* Interactive Follow-Up Engine */}
        <FollowUpEngine caseId={params.id} missingInfo={caseData.missing_info} />

        <footer className={styles.disclaimer}>
          {caseData.disclaimer}
        </footer>
      </div>
    );
  } catch (error) {
    console.error(error);
    return (
      <div className={styles.container}>
        <h1>Error Loading Results</h1>
        <p>There was a problem fetching the case results. Make sure the backend is running.</p>
        <Link href="/" className={styles.backBtn}>← Back to Input</Link>
      </div>
    );
  }
}
