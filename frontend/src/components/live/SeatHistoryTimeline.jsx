import React, { useState, useEffect } from 'react';
import { fetchSeatHistory } from '../../api/liveApi';
import styles from './SeatHistoryTimeline.module.css';

export default function SeatHistoryTimeline({ seatId }) {
  const [historyData, setHistoryData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Initial fetch
    let isMounted = true;
    
    const loadHistory = async () => {
      try {
        const data = await fetchSeatHistory(seatId);
        if (isMounted) {
          setHistoryData(data);
          setError(null);
        }
      } catch (err) {
        if (isMounted) setError(err.message);
      }
    };
    
    loadHistory();

    // 5-second polling per user requirement
    const interval = setInterval(loadHistory, 5000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [seatId]);

  if (error) {
    return <div className={styles.error}>Error: {error}</div>;
  }

  if (!historyData) {
    return <div className={styles.loading}>Loading timeline...</div>;
  }

  const durationSec = historyData.session_duration_seconds || 0;
  
  if (durationSec === 0) {
    return <div className={styles.empty}>Waiting for session...</div>;
  }

  // Calculate stats
  let totalOccupiedSec = 0;
  historyData.events.forEach(ev => {
    if (ev.status === 'occupied') {
      totalOccupiedSec += (ev.end_sec - ev.start_sec);
    }
  });

  const utilizationPercent = Math.round((totalOccupiedSec / durationSec) * 100);

  // Format MM:SS or HH:MM:SS
  const formatDuration = (totalSec) => {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    if (m >= 60) {
      const h = Math.floor(m / 60);
      const rm = m % 60;
      return `${h}h ${rm}m`;
    }
    return `${m}m ${s}s`;
  };

  return (
    <div className={styles.container}>
      <div className={styles.timelineBar}>
        {historyData.events.map((ev, i) => {
          const widthPercent = ((ev.end_sec - ev.start_sec) / durationSec) * 100;
          return (
            <div 
              key={i}
              className={`${styles.segment} ${ev.status === 'occupied' ? styles.occupied : styles.vacant}`}
              style={{ width: `${widthPercent}%` }}
              title={`${ev.status === 'occupied' ? 'Occupied' : 'Vacant'}: ${ev.start} → ${ev.end}`}
            />
          );
        })}
      </div>
      <div className={styles.statsRow}>
        <span>Occupied: {formatDuration(totalOccupiedSec)}</span>
        <span>Utilization: {utilizationPercent}%</span>
      </div>
    </div>
  );
}
