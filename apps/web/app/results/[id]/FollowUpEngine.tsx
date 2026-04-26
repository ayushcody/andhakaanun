'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

interface FollowUpEngineProps {
  caseId: string;
  missingInfo: string[];
}

export default function FollowUpEngine({ caseId, missingInfo }: FollowUpEngineProps) {
  const router = useRouter();
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Do not render if there's no missing info
  if (!missingInfo || missingInfo.length === 0) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    // Format payload and filter out empty answers
    const payload = {
      answers: missingInfo
        .map((q, i) => ({
          question: q,
          answer: answers[i]?.trim()
        }))
        .filter(item => item.answer)
    };

    if (payload.answers.length === 0) {
      alert("Please answer at least one question to refine the analysis.");
      return;
    }

    setIsSubmitting(true);

    try {
      const res = await fetch(`/api/proxy/cases/${caseId}/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (res.ok) {
        // Clear answers
        setAnswers({});
        // Refresh server components to fetch new data
        router.refresh();
      } else {
        const error = await res.json();
        alert(error?.detail?.message || 'Failed to refine analysis.');
      }
    } catch (err) {
      console.error(err);
      alert('Network error while refining.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="animate-slide-up delay-4" style={{ marginTop: '3rem' }}>
      <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1rem', color: '#fff' }}>
        Missing Legal Context
      </h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
        We identified missing context that could improve this analysis. Please answer any of the following to iteratively refine the argument quality:
      </p>
      
      <form onSubmit={handleSubmit} className="glass-panel" style={{ padding: '2rem' }}>
        {missingInfo.map((q, i) => (
          <div key={i} style={{ marginBottom: '1.5rem' }}>
            <label style={{ display: 'block', marginBottom: '0.75rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
              Question {i + 1}: {q}
            </label>
            <textarea
              value={answers[i] || ''}
              onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
              style={{
                width: '100%',
                padding: '0.75rem',
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                background: 'rgba(0,0,0,0.2)',
                color: '#fff',
                fontSize: '1rem',
                minHeight: '80px',
                resize: 'vertical',
                fontFamily: 'inherit'
              }}
              placeholder="Provide more context..."
            />
          </div>
        ))}
        
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
          <button 
            type="submit" 
            disabled={isSubmitting}
            style={{
              background: 'var(--accent-primary)',
              color: '#fff',
              border: 'none',
              padding: '0.75rem 2rem',
              borderRadius: '8px',
              fontSize: '1rem',
              fontWeight: 600,
              cursor: isSubmitting ? 'not-allowed' : 'pointer',
              opacity: isSubmitting ? 0.7 : 1,
              transition: 'background 0.2s',
              boxShadow: '0 0 15px rgba(58, 134, 255, 0.4)'
            }}
          >
            {isSubmitting ? 'Refining Analysis...' : 'Submit Answers'}
          </button>
        </div>
      </form>
    </section>
  );
}
