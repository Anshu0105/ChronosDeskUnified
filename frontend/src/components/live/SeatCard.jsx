import React from 'react';
import styles from './SeatCard.module.css';

/**
 * Renders a visually premium, glassmorphism status card for an individual seat.
 * 
 * @param {Object} props
 * @param {string} props.seat_id - The identifier (e.g. "A1")
 * @param {string} props.status - The real-time metric ("occupied" | "vacant" | "unknown")
 */
export default function SeatCard({ seat_id, status = "unknown", duration = 0, sat_at = null }) {
  // Dynamically attach vibrant CSS gradients mapping to backend statuses
  const activeClass = styles[status] || styles.unknown;

  const formatTime = (ts) => {
    if (!ts) return null;
    const date = new Date(ts * 1000);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const formatDuration = (sec) => {
    if (!sec || sec <= 0) return null;
    if (sec < 60) return `${Math.round(sec)}s`;
    const mins = Math.floor(sec / 60);
    const secs = Math.round(sec % 60);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className={styles.card}>
      {/* Top right hardware metric indicator */}
      <div className={`${styles.indicator} ${activeClass}`} title={status} />
      
      <h3 className={styles.title}>{seat_id}</h3>
      
      <div className={`${styles.statusBadge} ${activeClass}`}>
        {status}
      </div>

      {status === 'occupied' && (duration > 0 || sat_at) && (
        <div className={styles.timeInfo}>
          {sat_at && <span>Since: {formatTime(sat_at)}</span>}
          {duration > 0 && <span>Duration: {formatDuration(duration)}</span>}
        </div>
      )}
    </div>
  );
}

