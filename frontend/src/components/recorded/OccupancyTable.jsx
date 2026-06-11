import React from 'react';
import { formatTime } from '../../utils/recordedUtils';

export default function OccupancyTable({ perSeat }) {
  const getPctBadgeClass = (pct) => {
    if (pct > 60) return 'badge-success';
    if (pct >= 30) return 'badge-warning';
    return 'badge-danger';
  };

  return (
    <div className="card">
      <h3 className="card-title">Seat Occupancy Metrics</h3>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Seat</th>
              <th>Occupied Time</th>
              <th>Vacant Time</th>
              <th>Occupancy %</th>
              <th>Longest Streak</th>
              <th>Events</th>
            </tr>
          </thead>
          <tbody>
            {perSeat.map((seat) => (
              <tr key={seat.seat_id}>
                <td style={{ fontWeight: 'bold' }}>Seat {seat.seat_id}</td>
                <td>{formatTime(seat.totalOccupied)}</td>
                <td>{formatTime(seat.totalVacant)}</td>
                <td>
                  <span className={`badge ${getPctBadgeClass(seat.occupancyPct)}`}>
                    {seat.occupancyPct.toFixed(1)}%
                  </span>
                </td>
                <td>{formatTime(seat.longestStreak)}</td>
                <td>{seat.eventCount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
