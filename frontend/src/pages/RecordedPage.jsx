import React, { useState, useEffect, useRef } from 'react';
import DropZone from '../components/recorded/DropZone';
import OccupancyTable from '../components/recorded/OccupancyTable';
import TimelineChart from '../components/recorded/TimelineChart';
import BarChart from '../components/recorded/BarChart';
import PeakCard from '../components/recorded/PeakCard';
import { getSession, getSessions } from '../api/recordedApi';
import { computeAnalytics, formatTime } from '../utils/recordedUtils';
import '../styles/recorded.css';

export default function RecordedPage() {
  const [sessionId, setSessionId] = useState(null);
  const [sessionInfo, setSessionInfo] = useState(null);
  const [events, setEvents] = useState([]);
  const [history, setHistory] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [pollingStatus, setPollingStatus] = useState(null);

  const dashboardRef = useRef(null);

  // Fetch session history on mount
  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const data = await getSessions();
      setHistory(data);
    } catch (err) {
      console.error("Failed to load historical sessions:", err);
    } finally {
      setLoadingHistory(false);
    }
  };

  const loadSession = (id, attempts = 0) => {
    return new Promise(async (resolve, reject) => {
      try {
        const data = await getSession(id);
        
        if (data.session.status === 'processing') {
          if (attempts > 60) {
            setPollingStatus('failed');
            reject(new Error("Analysis is taking too long. Please try again."));
            return;
          }
          setPollingStatus('processing');
          setTimeout(() => {
            loadSession(id, attempts + 1).then(resolve).catch(reject);
          }, 3000);
          return;
        }
        
        if (data.session.status === 'failed') {
          setPollingStatus('failed');
          reject(new Error("Analysis failed during processing."));
          return;
        }
        
        setPollingStatus(null);
        setSessionId(id);
        setSessionInfo(data.session);
        setEvents(data.events);
        
        // Calculate derived analytics
        const results = computeAnalytics(data.events, data.session.video_duration_sec);
        setAnalytics(results);
        
        // Smooth scroll to Section 2 (Dashboard)
        setTimeout(() => {
          if (dashboardRef.current) {
            dashboardRef.current.scrollIntoView({ behavior: 'smooth' });
          }
        }, 100);
        
        // Refresh history list
        fetchHistory();
        resolve();
      } catch (err) {
        console.error(`Failed to load session ${id}:`, err);
        reject(err);
      }
    });
  };

  const handleAnalysisSuccess = async (id, totalSeats, durationSec) => {
    await loadSession(id);
  };

  const handleHistoryClick = async (id) => {
    try {
      await loadSession(id);
    } catch (err) {
      alert(`Error loading session: ${err.message}`);
    }
  };

  const handleExport = () => {
    if (!sessionId) return;
    const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    window.open(`${apiBaseUrl}/recorded/sessions/${sessionId}/export`, '_blank');
  };

  return (
    <div className="container">
      {/* Title Header */}
      <header>
        <h1>ChronosDesk Mark 2</h1>
        <p>Advanced Computer Vision Desk & Seat Occupancy Analyzer</p>
      </header>

      {/* Section 1: Drop Zone */}
      <div className="dashboard-section">
        <h2 className="section-header">Upload Video</h2>
        <DropZone onAnalysisSuccess={handleAnalysisSuccess} />
      </div>

      {/* Optional: Session History list (renders if no active session or as a drawer) */}
      {history.length > 0 && (
        <div className="dashboard-section history-section">
          <h2 className="section-header">Analysis History</h2>
          <div className="card">
            {loadingHistory ? (
              <div style={{ textAlign: 'center', color: 'var(--muted)' }}>Loading history...</div>
            ) : (
              <div className="history-list">
                {history.map((item) => (
                  <div 
                    key={item.id} 
                    className="history-item"
                    onClick={() => handleHistoryClick(item.id)}
                  >
                    <div className="history-item-details">
                      <span className="history-filename">{item.filename}</span>
                      <span className="history-meta">
                        Analyzed on: {new Date(item.analyzed_at).toLocaleString()}
                      </span>
                    </div>
                    <span className="badge" style={{ background: 'var(--accent-light)', color: 'var(--accent)' }}>
                      {item.total_seats} seats detected
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section 2: Dashboard (Visible only after session loads) */}
      {analytics && sessionInfo && (
        <div 
          ref={dashboardRef} 
          className="dashboard-container"
          style={{ scrollMarginTop: '20px' }}
        >
          <h2 className="section-header">Occupancy Analytics Dashboard</h2>
          
          {/* Summary Stat Cards */}
          <div className="stats-row">
            <div className="card stat-card">
              <span className="stat-label">Seats Detected</span>
              <span className="stat-value">{sessionInfo.total_seats}</span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Video Duration</span>
              <span className="stat-value">{formatTime(sessionInfo.video_duration_sec)}</span>
            </div>
            <div className="card stat-card">
              <span className="stat-label">Peak Occupancy</span>
              <span className="stat-value">
                {analytics.peakWindow.seat_count} seats <span style={{ fontSize: '1rem', color: 'var(--muted)', fontWeight: 'normal' }}>@ {formatTime(analytics.peakWindow.start_sec)}</span>
              </span>
            </div>
          </div>

          {/* Occupancy Table */}
          <OccupancyTable perSeat={analytics.perSeat} />

          {/* Timeline Chart */}
          <TimelineChart 
            perSeat={analytics.perSeat} 
            durationSec={sessionInfo.video_duration_sec} 
            peakWindow={analytics.peakWindow}
          />

          {/* Bar Chart */}
          <BarChart perSeat={analytics.perSeat} />

          {/* Peak Occupancy Callout Card */}
          <PeakCard peakWindow={analytics.peakWindow} />

          {/* Download CSV Action button */}
          <div className="action-area">
            <button className="btn btn-outline" onClick={handleExport}>
              <svg style={{ width: '20px', height: '20px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download CSV
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
