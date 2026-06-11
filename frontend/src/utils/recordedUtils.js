export function formatTime(seconds) {
  if (seconds === undefined || seconds === null || isNaN(seconds)) return '00:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function computeAnalytics(events, duration) {
  // Initialize perSeat analytics structure
  const seatIds = Array.from(new Set(events.map(e => e.seat_id))).sort((a, b) => a - b);
  const perSeat = {};
  
  seatIds.forEach(id => {
    perSeat[id] = {
      seat_id: id,
      totalOccupied: 0,
      totalVacant: duration,
      occupancyPct: 0,
      longestStreak: 0,
      eventCount: 0,
      events: []
    };
  });

  // Populate events per seat and compute totalOccupied, longestStreak, and eventCount
  events.forEach(event => {
    const seatId = event.seat_id;
    if (!perSeat[seatId]) return;
    
    const start = event.occ_start_sec;
    const end = event.occ_end_sec;
    const durationOfEvent = end - start;
    
    perSeat[seatId].events.push(event);
    perSeat[seatId].totalOccupied += durationOfEvent;
    perSeat[seatId].eventCount += 1;
    if (durationOfEvent > perSeat[seatId].longestStreak) {
      perSeat[seatId].longestStreak = durationOfEvent;
    }
  });

  // Calculate percentages and vacant times
  seatIds.forEach(id => {
    const seat = perSeat[id];
    seat.totalOccupied = Math.min(duration, seat.totalOccupied);
    seat.totalVacant = Math.max(0, duration - seat.totalOccupied);
    seat.occupancyPct = duration > 0 ? (seat.totalOccupied / duration) * 100 : 0;
    // Sort its events by start time
    seat.events.sort((a, b) => a.occ_start_sec - b.occ_start_sec);
  });

  // Slide a 60-second window across the video timeline to find peak window
  // Slide by 0.5 seconds increments
  let peakStart = 0;
  let peakEnd = 60;
  let maxSeatsCount = 0;
  
  if (duration <= 60) {
    // If video is shorter than 60s, window covers the whole video
    peakStart = 0;
    peakEnd = duration;
    // Count how many seats overlap this window
    const occupiedSeats = new Set();
    events.forEach(e => {
      if (e.occ_start_sec < duration && e.occ_end_sec > 0) {
        occupiedSeats.add(e.seat_id);
      }
    });
    maxSeatsCount = occupiedSeats.size;
  } else {
    for (let start = 0; start <= duration - 60; start += 0.5) {
      const end = start + 60;
      const occupiedSeats = new Set();
      
      events.forEach(e => {
        // Overlap check: e.start < window.end AND e.end > window.start
        if (e.occ_start_sec < end && e.occ_end_sec > start) {
          occupiedSeats.add(e.seat_id);
        }
      });
      
      if (occupiedSeats.size > maxSeatsCount) {
        maxSeatsCount = occupiedSeats.size;
        peakStart = start;
        peakEnd = end;
      }
    }
  }

  return {
    perSeat: Object.values(perSeat),
    peakWindow: {
      start_sec: peakStart,
      end_sec: peakEnd,
      seat_count: maxSeatsCount
    }
  };
}
