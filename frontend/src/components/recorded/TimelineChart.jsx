import React from 'react';
import { formatTime } from '../../utils/recordedUtils';

export default function TimelineChart({ perSeat, durationSec, peakWindow }) {
  const getSegments = (events) => {
    const segments = [];
    let currentPos = 0;
    
    // Sort events by start time
    const sortedEvents = [...events].sort((a, b) => a.occ_start_sec - b.occ_start_sec);
    
    sortedEvents.forEach(event => {
      const eventStart = Math.min(durationSec, Math.max(0, event.occ_start_sec));
      const eventEnd = Math.min(durationSec, Math.max(eventStart, event.occ_end_sec));
      
      // If there is a vacant gap before this event
      if (eventStart > currentPos) {
        segments.push({
          type: 'vacant',
          duration: eventStart - currentPos
        });
      }
      
      // Add the occupied segment
      const duration = eventEnd - eventStart;
      if (duration > 0) {
        segments.push({
          type: 'occupied',
          duration: duration
        });
      }
      
      currentPos = eventEnd;
    });
    
    // Final vacant segment if needed
    if (currentPos < durationSec) {
      segments.push({
        type: 'vacant',
        duration: durationSec - currentPos
      });
    }
    
    return segments;
  };

  // Generate X-axis ticks every 30 seconds
  const ticks = [];
  for (let t = 0; t <= durationSec; t += 30) {
    ticks.push(t);
  }
  // Ensure we show at least the end tick if the duration is not a multiple of 30 and is greater than 15s
  if (durationSec > 15 && ticks[ticks.length - 1] !== durationSec) {
    // If the last tick is too close to durationSec, replace it, otherwise add it
    if (durationSec - ticks[ticks.length - 1] < 10) {
      ticks[ticks.length - 1] = durationSec;
    } else {
      ticks.push(durationSec);
    }
  }

  return (
    <div className="card">
      <h3 className="card-title">Occupancy Timeline</h3>
      <div className="timeline-container">
        <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          {/* Peak Occupancy Vertical Line */}
          {peakWindow && peakWindow.start_sec !== undefined && durationSec > 0 && (
            <div 
              className="timeline-peak-line" 
              style={{ 
                left: `calc(80px + ${(peakWindow.start_sec / durationSec) * 100}% - ${(peakWindow.start_sec / durationSec) * 80}px)`
              }}
            >
              <div className="timeline-peak-line-label">
                Peak Start ({formatTime(peakWindow.start_sec)})
              </div>
            </div>
          )}
          
          {/* Seat Timeline Rows */}
          {perSeat.map((seat) => {
            const segments = getSegments(seat.events);
            return (
              <div key={seat.seat_id} className="timeline-row">
                <div className="timeline-label">Seat {seat.seat_id}</div>
                <div className="timeline-track-container">
                  <div className="timeline-track">
                    {segments.map((seg, idx) => {
                      const widthPct = durationSec > 0 ? (seg.duration / durationSec) * 100 : 0;
                      return (
                        <div 
                          key={idx}
                          className={seg.type === 'occupied' ? 'timeline-segment-occupied' : 'timeline-segment-vacant'}
                          style={{ width: `${widthPct}%` }}
                          title={`${seg.type.toUpperCase()}: ${seg.duration.toFixed(1)}s`}
                        />
                      );
                    })}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* X-Axis Timeline ticks */}
        <div className="timeline-axis">
          {ticks.map((tick) => {
            const positionPct = durationSec > 0 ? (tick / durationSec) * 100 : 0;
            return (
              <div 
                key={tick} 
                className="timeline-tick" 
                style={{ 
                  left: `calc(80px + ${positionPct}% - ${positionPct * 80 / 100}px)` 
                }}
              >
                <div className="timeline-tick-line"></div>
                <span>{formatTime(tick)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
