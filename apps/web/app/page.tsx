'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import styles from './page.module.css';

interface Badge {
  section: string;
  label: string;
}

export default function Home() {
  const router = useRouter();
  const [caseText, setCaseText] = useState('');
  const [location, setLocation] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [badges, setBadges] = useState<Badge[]>([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
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
          body: JSON.stringify({ text: caseText })
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
    if (!caseText || caseText.length < 50) return;
    
    setIsAnalyzing(true);
    
    try {
      // In this version we'll just hit the analyze endpoint (non-streaming for simplicity in V1 routing)
      // or redirect to a loading state in the results page that handles the stream.
      // Easiest is to fire a POST, get the ID, redirect to results page.
      const res = await fetch('/api/proxy/analyze-case', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          case_text: caseText, 
          location: location || 'India',
          groq_api_key: apiKey || undefined,
          stream: false 
        })
      });
      
      const data = await res.json();
      
      if (res.ok && data.case_id) {
        router.push(`/results/${data.case_id}`);
      } else {
        alert(data.detail?.message || 'Failed to analyze case. Please try again.');
        setIsAnalyzing(false);
      }
    } catch (err) {
      console.error(err);
      alert('Network error. Please make sure backend is running.');
      setIsAnalyzing(false);
    }
  };

  return (
    <main className={styles.main}>
      <div className={`${styles.hero} animate-slide-up`}>
        <h1 className={styles.title}>
          <span className="gradient-text">Andha</span>
          <span className="gradient-text-accent">Kaanun</span>
        </h1>
        <p className={styles.subtitle}>
          Instantly analyze any legal scenario using advanced RAG and AI reasoning mapped to Indian Law.
        </p>
      </div>

      <div className={`glass-panel ${styles.formContainer} animate-slide-up delay-1`}>
        <form onSubmit={handleSubmit}>
          <div className={styles.inputGroup}>
            <label className={styles.label} htmlFor="caseText">Case Narrative</label>
            <textarea
              id="caseText"
              className={styles.textarea}
              value={caseText}
              onChange={(e) => setCaseText(e.target.value)}
              placeholder="Describe what happened in detail... (Min 50 chars. e.g. 'A speeding car hit a pedestrian on FC Road...')"
              required
            />
            
            {/* Live Badges Container */}
            <div className={styles.badges}>
              {badges.map((badge, i) => (
                <span key={`${badge.section}-${i}`} className={styles.badge}>
                  {badge.label}
                </span>
              ))}
            </div>
          </div>

          <div className={styles.inputGroup}>
            <label className={styles.label} htmlFor="location">Location (State/City)</label>
            <input
              id="location"
              type="text"
              className={styles.input}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Maharashtra, Delhi, Pune..."
            />
          </div>

          <div className={styles.inputGroup}>
            <label className={styles.label} htmlFor="apiKey">Groq API Key (Optional)</label>
            <input
              id="apiKey"
              type="password"
              className={styles.input}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="gsk_..."
            />
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              Optional — overrides the server key. Get one free at{' '}
              <a href="https://console.groq.com/keys" target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)' }}>console.groq.com</a>.
            </p>
          </div>

          <button 
            type="submit" 
            className={styles.submitBtn}
            disabled={isAnalyzing || caseText.length < 50}
          >
            {isAnalyzing ? (
              <span className={styles.loadingSpinner}></span>
            ) : (
              'Analyze Case'
            )}
          </button>
        </form>
      </div>
    </main>
  );
}
