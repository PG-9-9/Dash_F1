"""Safety-car position simulation for replay frames."""

from __future__ import annotations

import numpy as np

def compute_safety_car_positions(frames, track_statuses, session):
    """
    Simulate safety car (SC) positions for each frame based on track status.
    
    The F1 API does not provide SC GPS data, so we simulate it:
    - SC appears when track status is "4" (Safety Car deployed)
    - SC enters from pitlane, travels along the track until the first car catches up
    - SC leads the pack while on track
    - When the SC period ends, SC accelerates away and enters the pitlane
    
    Handles edge cases:
    - The first car behind the SC may be a lapped car, not the race leader
    - Lapped cars can be let through (e.g. Abu Dhabi 2021 scenario)
    
    Each frame gets a 'safety_car' key with:
      - x, y: world coordinates of the SC
      - phase: 'deploying' | 'on_track' | 'returning' | None
      - alpha: 0.0-1.0 for fade in/out animation
    """
    if not frames or not track_statuses:
        return

    # Build reference polyline from the first driver's telemetry to get track shape
    try:
        fastest_lap = session.laps.pick_fastest()
        if fastest_lap is None:
            print("Safety Car: No fastest lap found, skipping SC position computation")
            return
        tel = fastest_lap.get_telemetry()
        if tel is None or tel.empty:
            print("Safety Car: No telemetry data, skipping SC position computation")
            return
        
        ref_xs = tel["X"].to_numpy().astype(float)
        ref_ys = tel["Y"].to_numpy().astype(float)
        ref_dist = tel["Distance"].to_numpy().astype(float)
        
        if len(ref_xs) < 10:
            print("Safety Car: Insufficient reference points, skipping")
            return
        
        # Interpolate reference to high density for smooth positioning
        from scipy.spatial import cKDTree
        t_old = np.linspace(0, 1, len(ref_xs))
        t_new = np.linspace(0, 1, 4000)
        ref_xs_dense = np.interp(t_new, t_old, ref_xs)
        ref_ys_dense = np.interp(t_new, t_old, ref_ys)
        ref_dist_dense = np.interp(t_new, t_old, ref_dist)
        
        # Build KD-Tree for fast position lookups
        ref_tree = cKDTree(np.column_stack((ref_xs_dense, ref_ys_dense)))
        
        # Cumulative distance along reference
        diffs = np.sqrt(np.diff(ref_xs_dense)**2 + np.diff(ref_ys_dense)**2)
        ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        ref_total = float(ref_cumdist[-1])
        
        # Compute normals (for pit lane offset)
        dx = np.gradient(ref_xs_dense)
        dy = np.gradient(ref_ys_dense)
        norm = np.sqrt(dx**2 + dy**2)
        norm[norm == 0] = 1.0
        ref_nx = -dy / norm
        ref_ny = dx / norm
        
    except Exception as e:
        print(f"Safety Car: Failed to build reference polyline: {e}")
        return

    # Identify SC deployment periods from track_statuses
    sc_periods = []
    for status in track_statuses:
        if str(status.get("status", "")) == "4":
            sc_periods.append({
                "start_time": status["start_time"],
                "end_time": status.get("end_time"),
            })
    
    if not sc_periods:
        print("Safety Car: No SC periods found in this session")
        return

    print(f"Safety Car: Found {len(sc_periods)} SC deployment period(s)")
    
    # ---- Constants ----
    # Deployment: SC exits pit, cruises on track at realistic SC speed, waits for leader
    DEPLOY_PIT_EXIT_DURATION = 4.0   # seconds to transition from pitlane to track surface
    DEPLOY_CRUISE_SPEED = 55.0       # m/s (~200 km/h, realistic safety car speed)
    DEPLOY_TOTAL_MAX = 120.0         # max seconds for deploying phase before forcing on_track
    
    # On track
    SC_OFFSET_METERS = 150           # how far ahead of the first car the SC drives
    
    # Returning: SC accelerates away, then enters pitlane
    RETURN_ACCEL_DURATION = 5.0      # seconds SC accelerates ahead of the field
    RETURN_ACCEL_SPEED = 400.0       # m/s (fast, to pull away from field)
    RETURN_PIT_ENTER_DURATION = 3.0  # seconds to transition from track into pitlane
    RETURN_TOTAL = RETURN_ACCEL_DURATION + RETURN_PIT_ENTER_DURATION  # total return phase
    
    # Pit lane entry/exit positions
    # Use a point ~10% of track ahead of start/finish as pit exit, and
    # a point ~90% as pit entry (approximates most circuits)
    PIT_OFFSET_INWARD = 400  # metres offset inward from track to simulate pitlane
    
    def _pos_at_dist(dist_m):
        """Get (x, y) on the reference line at a given cumulative distance (wraps around)."""
        d = dist_m % ref_total
        idx = int(np.searchsorted(ref_cumdist, d))
        idx = min(idx, len(ref_xs_dense) - 1)
        return float(ref_xs_dense[idx]), float(ref_ys_dense[idx])
    
    def _idx_at_dist(dist_m):
        """Get the reference index at a given cumulative distance (wraps around)."""
        d = dist_m % ref_total
        idx = int(np.searchsorted(ref_cumdist, d))
        return min(idx, len(ref_xs_dense) - 1)
    
    def _dist_of_point(x, y):
        """Project a point onto the reference line and return cumulative distance."""
        _, idx = ref_tree.query([x, y])
        return float(ref_cumdist[int(idx)])

    # Pit exit position: ~5% of track from start, offset inward
    pit_exit_track_dist = ref_total * 0.05
    pit_exit_idx = _idx_at_dist(pit_exit_track_dist)
    pit_exit_track_x, pit_exit_track_y = _pos_at_dist(pit_exit_track_dist)
    pit_exit_pit_x = float(ref_xs_dense[pit_exit_idx] + ref_nx[pit_exit_idx] * PIT_OFFSET_INWARD)
    pit_exit_pit_y = float(ref_ys_dense[pit_exit_idx] + ref_ny[pit_exit_idx] * PIT_OFFSET_INWARD)
    
    # Pit entry position: ~95% of track from start, offset inward
    pit_entry_track_dist = ref_total * 0.95
    pit_entry_idx = _idx_at_dist(pit_entry_track_dist)
    pit_entry_track_x, pit_entry_track_y = _pos_at_dist(pit_entry_track_dist)
    pit_entry_pit_x = float(ref_xs_dense[pit_entry_idx] + ref_nx[pit_entry_idx] * PIT_OFFSET_INWARD)
    pit_entry_pit_y = float(ref_ys_dense[pit_entry_idx] + ref_ny[pit_entry_idx] * PIT_OFFSET_INWARD)

    def get_first_car_behind_sc(frame, sc_dist_on_track):
        """
        Find the car that is closest behind the SC on the track.
        This might be a lapped car, not necessarily the race leader.
        Returns (code, x, y, track_dist) or (None, None, None, None).
        """
        drivers = frame.get("drivers", {})
        if not drivers:
            return None, None, None, None
        
        best_code = None
        best_gap = float('inf')  # smallest positive gap = closest behind
        best_x, best_y, best_dist = None, None, None
        
        for code, pos in drivers.items():
            dx, dy = pos.get("x", 0.0), pos.get("y", 0.0)
            d_track = _dist_of_point(dx, dy)
            
            # Gap = how far behind the SC this car is (on track, wrapping)
            gap = (sc_dist_on_track - d_track) % ref_total
            
            # We want the car with the smallest positive gap (closest behind SC)
            # Ignore cars that are essentially at the same position (< 10m)
            if 10.0 < gap < best_gap:
                best_gap = gap
                best_code = code
                best_x = dx
                best_y = dy
                best_dist = d_track
        
        return best_code, best_x, best_y, best_dist

    def get_leader_info(frame):
        """Get the race leader's (code, x, y, track_dist, total_progress)."""
        drivers = frame.get("drivers", {})
        if not drivers:
            return None, None, None, None, None
        best_code = None
        best_progress = -1
        for code, pos in drivers.items():
            lap = pos.get("lap", 1)
            dist = pos.get("dist", 0)
            progress = (max(lap, 1) - 1) * ref_total + dist
            if progress > best_progress:
                best_progress = progress
                best_code = code
        if best_code:
            px = drivers[best_code]["x"]
            py = drivers[best_code]["y"]
            return best_code, px, py, _dist_of_point(px, py), best_progress
        return None, None, None, None, None

    # ---- Per-SC-period state tracking ----
    # We process frames sequentially so we can accumulate SC position state
    
    # For each SC period, track the SC's cumulative position on the track
    sc_state = {}  # keyed by sc_period index
    
    for fi, frame in enumerate(frames):
        t = frame["t"]
        
        # Check if current time falls in any SC period
        active_sc = None
        active_sc_idx = None
        for sci, sc in enumerate(sc_periods):
            sc_start = sc["start_time"]
            sc_end = sc.get("end_time")
            effective_end = (sc_end + RETURN_TOTAL) if sc_end else None
            
            if t >= sc_start and (effective_end is None or t < effective_end):
                active_sc = sc
                active_sc_idx = sci
                break
        
        if active_sc is None:
            frame["safety_car"] = None
            continue
        
        sc_start = active_sc["start_time"]
        sc_end = active_sc.get("end_time")
        elapsed = t - sc_start
        
        # Initialize state for this SC period if not already done
        if active_sc_idx not in sc_state:
            sc_state[active_sc_idx] = {
                "track_dist": pit_exit_track_dist,  # SC starts at pit exit on track
                "caught_up": False,                  # has the leader caught the SC?
                "last_t": t,
                "return_start_dist": None,           # track dist when return phase begins
                "prev_leader_dist": None,            # for tracking leader speed
            }
        
        state = sc_state[active_sc_idx]
        dt_frame = max(0.0, t - state["last_t"])
        state["last_t"] = t
        
        # ========================
        # PHASE 1: DEPLOYING
        # ========================
        if elapsed < DEPLOY_PIT_EXIT_DURATION:
            # Sub-phase 1a: SC transitioning from pitlane onto the track surface
            phase = "deploying"
            progress = elapsed / DEPLOY_PIT_EXIT_DURATION  # 0 -> 1
            alpha = progress
            
            # Smooth interpolation from pit exit (off-track) to pit exit (on-track)
            # Use ease-in-out for smooth animation
            smooth_t = 0.5 - 0.5 * np.cos(progress * np.pi)  # smoothstep
            sc_x = pit_exit_pit_x + smooth_t * (pit_exit_track_x - pit_exit_pit_x)
            sc_y = pit_exit_pit_y + smooth_t * (pit_exit_track_y - pit_exit_pit_y)
            
        elif elapsed < DEPLOY_PIT_EXIT_DURATION + DEPLOY_TOTAL_MAX and not state["caught_up"]:
            # Sub-phase 1b: SC cruises on track at a realistic pace,
            # slightly slower than the field so the leader catches up naturally.
            phase = "deploying"
            alpha = 1.0
            
            # Estimate the leader's actual speed from telemetry position changes
            leader_code, _, _, leader_dist, _ = get_leader_info(frame)
            
            if leader_code is not None:
                # Track leader speed by comparing consecutive positions
                if state["prev_leader_dist"] is not None and dt_frame > 0:
                    leader_moved = leader_dist - state["prev_leader_dist"]
                    # Handle wrapping around start/finish line
                    if leader_moved > ref_total / 2:
                        leader_moved -= ref_total
                    elif leader_moved < -ref_total / 2:
                        leader_moved += ref_total
                    leader_speed = abs(leader_moved) / dt_frame
                else:
                    leader_speed = 55.0  # default ~200 km/h on first frame
                state["prev_leader_dist"] = leader_dist
                
                # SC cruises at 80% of the leader's speed
                # This guarantees the leader always catches up, but SC is still moving
                sc_speed = max(20.0, min(leader_speed * 0.8, 60.0))  # clamp 20-60 m/s
            else:
                sc_speed = DEPLOY_CRUISE_SPEED  # fallback
            
            # Advance SC along the track
            state["track_dist"] += sc_speed * dt_frame
            state["track_dist"] = state["track_dist"] % ref_total
            
            sc_x, sc_y = _pos_at_dist(state["track_dist"])
            
            # Check if the LEADER has caught up behind the SC
            if leader_code is not None:
                # How far ahead is the SC of the leader? (forward direction on track)
                gap_ahead = (state["track_dist"] - leader_dist) % ref_total
                
                # Leader is close behind the SC -> transition to on_track
                if gap_ahead <= SC_OFFSET_METERS + 50:
                    state["caught_up"] = True
                    
        elif sc_end is not None and t >= sc_end:
            # ========================  
            # PHASE 3: RETURNING
            # ========================
            return_elapsed = t - sc_end
            
            if state["return_start_dist"] is None:
                state["return_start_dist"] = state["track_dist"]
            
            if return_elapsed < RETURN_ACCEL_DURATION:
                # Sub-phase 3a: SC accelerates away from the field
                phase = "returning"
                alpha = 1.0
                
                # SC speeds up along the track, pulling away from the pack
                state["track_dist"] += RETURN_ACCEL_SPEED * dt_frame
                state["track_dist"] = state["track_dist"] % ref_total
                
                sc_x, sc_y = _pos_at_dist(state["track_dist"])
                
            else:
                # Sub-phase 3b: SC transitions from track surface into the pitlane
                phase = "returning"
                pit_enter_elapsed = return_elapsed - RETURN_ACCEL_DURATION
                progress = min(1.0, pit_enter_elapsed / RETURN_PIT_ENTER_DURATION)
                alpha = max(0.0, 1.0 - progress)
                
                # Get SC's current track position (frozen at end of accel phase)
                # and interpolate toward pit entry point
                track_x, track_y = _pos_at_dist(state["track_dist"])
                
                smooth_t = 0.5 - 0.5 * np.cos(progress * np.pi)  # smoothstep
                sc_x = track_x + smooth_t * (pit_entry_pit_x - track_x)
                sc_y = track_y + smooth_t * (pit_entry_pit_y - track_y)
        else:
            # ========================
            # PHASE 2: ON TRACK
            # ========================
            # SC leads the race, positioned ahead of the race leader.
            # Uses total race progress (laps + distance) to find the leader,
            # which avoids the start/finish line wrapping bug.
            phase = "on_track"
            alpha = 1.0
            state["caught_up"] = True  # ensure we mark as caught up
            
            # Find the RACE LEADER (by total progress: laps * track_length + distance)
            # This is robust across the start/finish line because it uses lap count.
            leader_code, leader_x, leader_y, leader_dist, _ = get_leader_info(frame)
            
            if leader_code is not None:
                # Position SC directly at a fixed offset ahead of the leader.
                # Since the leader moves smoothly frame-by-frame, the SC follows
                # smoothly as well — like a shadow but ahead.
                target_dist = (leader_dist + SC_OFFSET_METERS) % ref_total
                state["track_dist"] = target_dist
            else:
                # Fallback: no leader found, advance slowly
                state["track_dist"] += 100.0 * dt_frame
                state["track_dist"] = state["track_dist"] % ref_total
            
            sc_x, sc_y = _pos_at_dist(state["track_dist"])
        
        frame["safety_car"] = {
            "x": round(sc_x, 2),
            "y": round(sc_y, 2),
            "phase": phase,
            "alpha": round(alpha, 3),
        }

    # Count frames with SC data
    sc_frame_count = sum(1 for f in frames if f.get("safety_car") is not None)
    print(f"Safety Car: Computed positions for {sc_frame_count} frames")
