'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';

interface FollowUpEngineProps {
  caseId: string;
  missingInfo: string[];
}

export default function FollowUpEngine({ caseId, missingInfo }: FollowUpEngineProps) {
  const router = useRouter();
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Do not render if there's no missing info
  if (!missingInfo || missingInfo.length === 0) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Format payload and filter out empty answers
    const payload = {
      answers: missingInfo
        .map((q, i) => ({
          question: q,
          answer: answers[i]?.trim(),
        }))
        .filter((item) => item.answer),
    };

    if (payload.answers.length === 0) {
      setError('Answer at least one question to refine the analysis.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`/api/proxy/cases/${caseId}/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        setAnswers({});
        // Re-render the server component so it fetches the refined analysis.
        router.refresh();
      } else {
        const body = await res.json();
        setError(body?.detail?.message || 'Refinement failed. Please try again.');
      }
    } catch (err) {
      console.error(err);
      setError('Could not reach the analysis service.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const answered = Object.values(answers).filter((a) => a.trim()).length;

  return (
    <section className={`${styles.followUp} reveal`} style={{ '--i': 5 } as React.CSSProperties}>
      <h2 className={styles.h2}>What would sharpen this analysis</h2>
      <p className={styles.blockLede}>
        These facts are missing from your account. Answer any of them and the case is analyzed again with your
        answers added.
      </p>

      <form onSubmit={handleSubmit} className={styles.followForm}>
        {missingInfo.map((q, i) => (
          <div key={i} className={styles.question}>
            <label htmlFor={`fu-${i}`} className={styles.questionLabel}>
              <span className={`mono ${styles.qIndex}`}>Q{i + 1}</span>
              {q}
            </label>
            <textarea
              id={`fu-${i}`}
              className={`field ${styles.answer}`}
              value={answers[i] || ''}
              onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
              placeholder="Leave blank if you don't know"
              rows={2}
            />
          </div>
        ))}

        <div className={styles.followActions}>
          <span className="field-help">
            {answered} of {missingInfo.length} answered
          </span>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? 'Re-analyzing...' : 'Refine analysis'}
          </button>
        </div>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
