import React from 'react';
import { formatTime } from '../../utils/recordedUtils';

export default function PeakCard({ peakWindow }) {
  if (!peakWindow) return null;

  return (
    <div className="card peak-card">
      <div className="peak-card-content">
        <svg 
          className="peak-card-icon" 
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor" 
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m12.728 12.728l.707-.707M12 8a4 4 0 100 8 4 4 0 000-8z" />
        </svg>
        <div className="peak-card-text">
          Between <span className="peak-highlight">{formatTime(peakWindow.start_sec)}</span> and{' '}
          <span className="peak-highlight">{formatTime(peakWindow.end_sec)}</span>,{' '}
          <span className="peak-highlight">{peakWindow.seat_count}</span>{' '}
          {peakWindow.seat_count === 1 ? 'seat was' : 'seats were'} occupied simultaneously.
        </div>
      </div>
    </div>
  );
}
