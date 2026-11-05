'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';

interface Badge {
  section: string;
  label: string;
}

const MIN_CHARS = 50;
const MAX_CHARS = 3000;

const EXAMPLES: { label: string; text: string; location: string }[] = [
  {
    label: 'Hit and run',
    location: 'Pune, Maharashtra',
    text:
      'On the night of 12 March, a speeding car hit a pedestrian who was crossing FC Road near the Deccan bus stop. ' +
      'The driver did not stop; it was a hit and run, and the car was later traced through CCTV footage from a nearby shop. ' +
      'The pedestrian, a 58-year-old man, suffered a serious injury: a fractured leg and a head wound.',
  },
  {
    label: 'Online fraud',
    location: 'Bengaluru, Karnataka',
    text:
      'A caller posing as a bank officer said my account would be blocked and asked me to share an OTP. ' +
      'Minutes later Rs. 48,000 was debited in three UPI transfers. The same day my email account was hacked and the ' +
      'password changed. I have the call log, the SMS alerts and the bank statement. This looks like a planned fraud.',
  },
];

const STEPS: { verb: string; text: string }[] = [
  { verb: 'Detect', text: 'Reads the narrative for offences, domain and location.' },
  { verb: 'Retrieve', text: 'Pulls matching sections from the Indian law index.' },
  { verb: 'Argue', text: 'Drafts prosecution and defense from those sections only.' },
  { verb: 'Ask', text: 'Lists the facts that would change the analysis.' },
];

export default function Home() {
  const router = useRouter();
  const [caseText, setCaseText] = useState('');
  const [location, setLocation] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [badges, setBadges] = useState<Badge[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref for debouncing jurisdiction detection
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Debounce jurisdiction detect to avoid spamming the API
    if (caseText.length < 15) {
      setBadges([]);
      return;
    }

    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    timeoutRef.current = setTimeout(async () => {
      try {
        const res = await fetch('/api/proxy/detect-jurisdiction', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: caseText }),
        });
        if (res.ok) {
          const data = await res.json();
          setBadges(data.badges || []);
        }
      } catch (err) {
        console.error('Failed to detect jurisdiction live', err);
      }
    }, 500);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [caseText]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!caseText || caseText.length < MIN_CHARS) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      // Non-streaming request: get the case id back, then open the results page.
      const res = await fetch('/api/proxy/analyze-case', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_text: caseText,
          location: location || 'India',
          groq_api_key: apiKey || undefined,
          stream: false,
        }),
      });

      const data = await res.json();

      if (res.ok && data.case_id) {
        router.push(`/results/${data.case_id}`);
      } else {
        setError(data.detail?.message || 'The analysis failed. Please try again.');
        setIsAnalyzing(false);
      }
    } catch (err) {
      console.error(err);
      setError('Could not reach the analysis service. Check that the API is running on port 8000.');
      setIsAnalyzing(false);
    }
  };

  const remaining = MIN_CHARS - caseText.length;

  return (
    <div className={styles.page}>
      <header className={styles.topbar}>
        <span className="wordmark">
          Andha<span>Kaanun</span>
        </span>
        <a
          className={styles.topLink}
          href="https://github.com/ayushcody/andhakaanun"
          target="_blank"
          rel="noreferrer"
        >
          Source
        </a>
      </header>

      <main className={styles.main}>
        <section className={styles.intro}>
          <h1 className={`${styles.title} reveal`}>Both sides of the case, grounded in Indian law.</h1>
          <p className={`${styles.lede} reveal`} style={{ '--i': 1 } as React.CSSProperties}>
            Describe what happened. Get the sections that apply, the prosecution and defense arguments, and the
            facts still missing.
          </p>

          <dl className={`${styles.steps} reveal`} style={{ '--i': 2 } as React.CSSProperties}>
            {STEPS.map((s) => (
              <div key={s.verb} className={styles.step}>
                <dt>{s.verb}</dt>
                <dd>{s.text}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={`${styles.panel} reveal`} style={{ '--i': 1 } as React.CSSProperties}>
          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.fieldBlock}>
              <div className={styles.labelRow}>
                <label className="field-label" htmlFor="caseText">
                  What happened?
                </label>
                <div className={styles.examples}>
                  <span>Try:</span>
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.label}
                      type="button"
                      className={styles.exampleBtn}
                      onClick={() => {
                        setCaseText(ex.text);
                        setLocation(ex.location);
                      }}
                    >
                      {ex.label}
                    </button>
                  ))}
                </div>
              </div>
              <textarea
                id="caseText"
                className={`field ${styles.narrative}`}
                value={caseText}
                maxLength={MAX_CHARS}
                onChange={(e) => setCaseText(e.target.value)}
                placeholder="Who was involved, what happened, when and where. Plain language is fine."
                required
              />
              <div className={styles.metaRow}>
                <span className="field-help">
                  {remaining > 0 ? `${remaining} more characters needed` : 'Ready to analyze'}
                </span>
                <span className={`mono ${styles.counter}`}>
                  {caseText.length} / {MAX_CHARS}
                </span>
              </div>
            </div>

            <div className={styles.detected} aria-live="polite">
              <span className={styles.detectedLabel}>Likely sections</span>
              {badges.length > 0 ? (
                <ul className={styles.badges}>
                  {badges.map((badge, i) => (
                    <li key={`${badge.section}-${i}`} className={`mono ${styles.badge}`}>
                      {badge.label}
                    </li>
                  ))}
                </ul>
              ) : (
                <span className={styles.detectedEmpty}>Detected as you type</span>
              )}
            </div>

            <div className={styles.fieldBlock}>
              <label className="field-label" htmlFor="location">
                Where did it happen?
              </label>
              <input
                id="location"
                type="text"
                className="field"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="City or state, e.g. Pune, Maharashtra"
              />
            </div>

            <details className={styles.keyDetails}>
              <summary>Use your own Groq API key</summary>
              <div className={styles.keyBody}>
                <label className="field-label" htmlFor="apiKey">
                  Groq API key
                </label>
                <input
                  id="apiKey"
                  type="password"
                  className="field"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="gsk_..."
                  autoComplete="off"
                />
                <p className="field-help">
                  Optional. Overrides the server key for this request. Get one at{' '}
                  <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" className={styles.inlineLink}>
                    console.groq.com
                  </a>
                  .
                </p>
              </div>
            </details>

            <button type="submit" className={`btn-primary ${styles.submit}`} disabled={isAnalyzing || caseText.length < MIN_CHARS}>
              {isAnalyzing ? 'Analyzing case...' : 'Analyze case'}
            </button>
            {isAnalyzing && <div className={styles.progress} aria-hidden="true" />}
            {error && (
              <p className="inline-error" role="alert">
                {error}
              </p>
            )}
          </form>
        </section>
      </main>

      <footer className={styles.footer}>
        AI-generated analysis for understanding a situation. It is not legal advice.
      </footer>
    </div>
  );
}
