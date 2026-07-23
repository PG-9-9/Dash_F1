import math
import os
import pickle
import sys
from datetime import timedelta, date
from multiprocessing import Pool, cpu_count
from typing import Callable

import fastf1
import fastf1.plotting
import numpy as np
import pandas as pd

from src.lib.settings import get_settings
from src.lib.time import parse_time_string
from src.lib.tyres import get_tyre_compound_int

from src.data.cache_session import get_driver_colors


FPS = 25
DT = 1 / FPS


def _process_single_driver(args):
    """Process telemetry data for a single driver - must be top-level for multiprocessing"""
    driver_no, session, driver_code = args

    print(f"Getting telemetry for driver: {driver_code}")

    laps_driver = session.laps.pick_drivers(driver_no)
    if laps_driver.empty:
        return None

    driver_max_lap = laps_driver.LapNumber.max() if not laps_driver.empty else 0

    t_all = []
    x_all = []
    y_all = []
    race_dist_all = []
    rel_dist_all = []
    lap_numbers = []
    tyre_compounds = []
    tyre_life_all = []
    speed_all = []
    gear_all = []
    drs_all = []
    throttle_all = []
    brake_all = []

    total_dist_so_far = 0.0

    # iterate laps in order
    for _, lap in laps_driver.iterlaps():
        # get telemetry for THIS lap only
        try:
            lap_tel = lap.get_telemetry()
        except KeyError as e:
            # Handle case where FastF1 fails to merge car and position data
            # due to empty position telemetry (missing 'Date' column)
            if "'Date'" in str(e):
                print(f"Warning: Skipping lap {lap.LapNumber} for driver {driver_code} due to missing position telemetry")
                continue
            else:
                # Re-raise if it's a different KeyError
                raise
        lap_number = lap.LapNumber
        tyre_compund_as_int = get_tyre_compound_int(lap.Compound)
        tyre_life = lap.TyreLife if pd.notna(lap.TyreLife) else 0

        if lap_tel.empty:
            continue

        t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
        x_lap = lap_tel["X"].to_numpy()
        y_lap = lap_tel["Y"].to_numpy()
        d_lap = lap_tel["Distance"].to_numpy()
        rd_lap = lap_tel["RelativeDistance"].to_numpy()
        speed_kph_lap = lap_tel["Speed"].to_numpy()
        gear_lap = lap_tel["nGear"].to_numpy()
        drs_lap = lap_tel["DRS"].to_numpy()
        throttle_lap = lap_tel["Throttle"].to_numpy()
        brake_lap = lap_tel["Brake"].to_numpy().astype(float)

        # race distance = distance before this lap + distance within this lap
        race_d_lap = total_dist_so_far + d_lap

        t_all.append(t_lap)
        x_all.append(x_lap)
        y_all.append(y_lap)
        race_dist_all.append(race_d_lap)
        rel_dist_all.append(rd_lap)
        lap_numbers.append(np.full_like(t_lap, lap_number))
        tyre_compounds.append(np.full_like(t_lap, tyre_compund_as_int))
        tyre_life_all.append(np.full_like(t_lap, tyre_life))
        speed_all.append(speed_kph_lap)
        gear_all.append(gear_lap)
        drs_all.append(drs_lap)
        throttle_all.append(throttle_lap)
        brake_all.append(brake_lap)

    if not t_all:
        return None

    # Concatenate all arrays at once for better performance
    all_arrays = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                  lap_numbers, tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all = [np.concatenate(arr) for arr in all_arrays]

    # Sort all arrays by time in one operation
    order = np.argsort(t_all)
    all_data = [t_all, x_all, y_all, race_dist_all, rel_dist_all, 
                lap_numbers, tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all]
    
    t_all, x_all, y_all, race_dist_all, rel_dist_all, lap_numbers, \
    tyre_compounds, tyre_life_all, speed_all, gear_all, drs_all = [arr[order] for arr in all_data]

    throttle_all = np.concatenate(throttle_all)[order]
    brake_all = np.concatenate(brake_all)[order]

    print(f"Completed telemetry for driver: {driver_code}")

    return {
        "code": driver_code,
        "data": {
            "t": t_all,
            "x": x_all,
            "y": y_all,
            "dist": race_dist_all,
            "rel_dist": rel_dist_all,
            "lap": lap_numbers,
            "tyre": tyre_compounds,
            "tyre_life": tyre_life_all,
            "speed": speed_all,
            "gear": gear_all,
            "drs": drs_all,
            "throttle": throttle_all,
            "brake": brake_all,
        },
        "t_min": t_all.min(),
        "t_max": t_all.max(),
        "max_lap": driver_max_lap,
    }


from src.data.safety_car import compute_safety_car_positions

def get_race_telemetry(session, session_type="R", progress_callback: Callable[[float, str], None] | None = None):
    def report(progress, message):
        if progress_callback:
            progress_callback(max(0.0, min(1.0, progress)), message)

    event_name = str(session).replace(" ", "_")
    cache_suffix = "sprint" if session_type == "S" else "race"

    # Check if this data has already been computed

    try:
        if "--refresh-data" not in sys.argv:
            with open(
                f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "rb"
            ) as f:
                frames = pickle.load(f)
                print(f"Loaded precomputed {cache_suffix} telemetry data.")
                print("The replay should begin in a new window shortly!")
                report(1.0, "Loaded cached telemetry")
                return frames
    except FileNotFoundError:
        pass  # Need to compute from scratch

    drivers = session.drivers

    driver_codes = {num: session.get_driver(num)["Abbreviation"] for num in drivers}

    driver_data = {}

    global_t_min = None
    global_t_max = None

    max_lap_number = 0

    # 1. Get all of the drivers telemetry data using multiprocessing
    # Prepare arguments for parallel processing
    print(f"Processing {len(drivers)} drivers in parallel...")
    report(0.10, "Collecting driver telemetry")
    driver_args = [
        (driver_no, session, driver_codes[driver_no]) for driver_no in drivers
    ]

    num_processes = min(cpu_count(), len(drivers))

    with Pool(processes=num_processes) as pool:
        results = []
        for index, result in enumerate(pool.imap_unordered(_process_single_driver, driver_args), start=1):
            results.append(result)
            report(0.10 + (index / max(1, len(driver_args)) * 0.45), f"Processed {index}/{len(driver_args)} drivers")

    # Process results
    for result in results:
        if result is None:
            continue

        code = result["code"]
        driver_data[code] = result["data"]

        t_min = result["t_min"]
        t_max = result["t_max"]
        max_lap_number = max(max_lap_number, result["max_lap"])

        global_t_min = t_min if global_t_min is None else min(global_t_min, t_min)
        global_t_max = t_max if global_t_max is None else max(global_t_max, t_max)

    # Ensure we have valid time bounds
    if global_t_min is None or global_t_max is None:
        raise ValueError("No valid telemetry data found for any driver")

    # 2. Create a timeline (start from zero)
    report(0.60, "Aligning telemetry timeline")
    timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min

    # 3. Resample each driver's telemetry (x, y) onto the common timeline
    report(0.75, "Resampling driver telemetry")
    resampled_data = {}
    max_tyre_life_map = {}

    for code, data in driver_data.items():
        t = data["t"] - global_t_min  # Shift

        # ensure sorted by time
        order = np.argsort(t)
        t_sorted = t[order]

        # Vectorize all resampling in one operation for speed
        arrays_to_resample = [
            data["x"][order],
            data["y"][order],
            data["dist"][order],
            data["rel_dist"][order],
            data["lap"][order],
            data["tyre"][order],
            data["tyre_life"][order],
            data["speed"][order],
            data["gear"][order],
            data["drs"][order],
            data["throttle"][order],
            data["brake"][order],
        ]

        resampled = [np.interp(timeline, t_sorted, arr) for arr in arrays_to_resample]
        x_resampled, y_resampled, dist_resampled, rel_dist_resampled, lap_resampled, \
        tyre_resampled, tyre_life_resampled, speed_resampled, gear_resampled, drs_resampled, throttle_resampled, brake_resampled = resampled
 
        resampled_data[code] = {
            "t": timeline,
            "x": x_resampled,
            "y": y_resampled,
            "dist": dist_resampled,  # race distance (metres since Lap 1 start)
            "rel_dist": rel_dist_resampled,
            "lap": lap_resampled,
            "tyre": tyre_resampled,
            "tyre_life": tyre_life_resampled,
            "speed": speed_resampled,
            "gear": gear_resampled,
            "drs": drs_resampled,
            "throttle": throttle_resampled,
            "brake": brake_resampled,
        }

        for t_int in np.unique(tyre_resampled):
            mask = tyre_resampled == t_int
            c_max = np.nanmax(tyre_life_resampled[mask])
            if not np.isnan(c_max):
                max_tyre_life_map[int(t_int)] = max(max_tyre_life_map.get(int(t_int), 1), int(c_max))

    # 4. Incorporate track status data into the timeline (for safety car, VSC, etc.)
    report(0.85, "Building replay frames")

    track_status = session.track_status

    formatted_track_statuses = []

    for status in track_status.to_dict("records"):
        seconds = timedelta.total_seconds(status["Time"])

        start_time = seconds - global_t_min  # Shift to match timeline
        end_time = None

        # Set the end time of the previous status

        if formatted_track_statuses:
            formatted_track_statuses[-1]["end_time"] = start_time

        formatted_track_statuses.append(
            {
                "status": status["Status"],
                "start_time": start_time,
                "end_time": end_time,
            }
        )

    # 4a. Parse race control messages (flags, penalties, SC/VSC, DRS, etc.)
    report(0.92, "Computing race control data")
    formatted_rc_messages = []
    rc_messages = getattr(session, "race_control_messages", None)

    def _safe_str(val, as_int=False):
        """Convert a value to string, returning '' for None/NaN."""
        if val is None:
            return ""
        try:
            if isinstance(val, float) and math.isnan(val):
                return ""
        except (TypeError, ValueError):
            pass
        if as_int:
            try:
                return str(int(float(val)))
            except (ValueError, TypeError):
                return str(val)
        return str(val)

    if rc_messages is not None and not rc_messages.empty:
        for msg in rc_messages.to_dict("records"):
            time_val = msg["Time"]
            if hasattr(time_val, 'total_seconds'):
                # Timedelta (session-relative) — same as track_status
                seconds = time_val.total_seconds()
            else:
                # Timestamp (absolute) — subtract the data stream origin
                seconds = (time_val - session.t0_date).total_seconds()
            msg_time = seconds - global_t_min

            if msg_time > 0.0:
                formatted_rc_messages.append({
                    "time": round(msg_time, 3),
                    "category": _safe_str(msg.get("Category", "")),
                    "message": _safe_str(msg.get("Message", "")),
                    "flag": _safe_str(msg.get("Flag", "")),
                    "scope": _safe_str(msg.get("Scope", "")),
                    "sector": _safe_str(msg.get("Sector", ""), as_int=True),
                    "racing_number": _safe_str(msg.get("RacingNumber", ""), as_int=True),
                })
        formatted_rc_messages.sort(key=lambda m: m["time"])

    # 4.1. Resample weather data onto the same timeline for playback
    weather_resampled = None
    weather_df = getattr(session, "weather_data", None)
    if weather_df is not None and not weather_df.empty:
        try:
            weather_times = (
                weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            )
            if len(weather_times) > 0:
                order = np.argsort(weather_times)
                weather_times = weather_times[order]

                def _maybe_get(name):
                    return (
                        weather_df[name].to_numpy()[order]
                        if name in weather_df
                        else None
                    )

                def _resample(series):
                    if series is None:
                        return None
                    return np.interp(timeline, weather_times, series)

                track_temp = _resample(_maybe_get("TrackTemp"))
                air_temp = _resample(_maybe_get("AirTemp"))
                humidity = _resample(_maybe_get("Humidity"))
                wind_speed = _resample(_maybe_get("WindSpeed"))
                wind_direction = _resample(_maybe_get("WindDirection"))
                rainfall_raw = _maybe_get("Rainfall")
                rainfall = (
                    _resample(rainfall_raw.astype(float))
                    if rainfall_raw is not None
                    else None
                )

                weather_resampled = {
                    "track_temp": track_temp,
                    "air_temp": air_temp,
                    "humidity": humidity,
                    "wind_speed": wind_speed,
                    "wind_direction": wind_direction,
                    "rainfall": rainfall,
                }
        except Exception as e:
            print(f"Weather data could not be processed: {e}")

    #4.2. Aggregating Driver pit-in and pit-out data for Pitstop leaderboard indicator
    pit_windows={}
    laps=session.laps

    for driver_no in drivers:
        drv=session.get_driver(driver_no)["Abbreviation"]
        driver_laps=laps.pick_drivers(drv)
        windows=[]

        for _, lap in driver_laps.iterrows():
            pit_in=lap.get("PitInTime")
            pit_out=lap.get("PitOutTime")

            if pd.notna(pit_in):
                start=pit_in.total_seconds()
                if pd.notna(pit_out):
                    end=pit_out.total_seconds()
                else:
                    end=start+40 #Error Rare case
                
                windows.append((start,end))
        pit_windows[drv]=windows
    
    #Adjusting pit windows to the telemetry timeline
    pit_windows_shifted={}
    for drv, windows in pit_windows.items():
        shifted=[]
        for start,end in windows:
            shifted.append((start-global_t_min,end-global_t_min))
        pit_windows_shifted[drv]=shifted
    
    print("PIT WINDOWS: ", pit_windows)

    # 5. Build the frames + LIVE LEADERBOARD
    frames = []
    num_frames = len(timeline)

    # Pre-extract data references for faster access
    driver_codes = list(resampled_data.keys())
    driver_arrays = {code: resampled_data[code] for code in driver_codes}

    for i in range(num_frames):
        t = timeline[i]
        snapshot = []
        for code in driver_codes:
            d = driver_arrays[code]
            snapshot.append({
                "code": code,
                "dist": float(d["dist"][i]),
                "x": float(d["x"][i]),
                "y": float(d["y"][i]),
                "lap": int(round(d["lap"][i])),
                "rel_dist": float(d["rel_dist"][i]),
                "tyre": float(d["tyre"][i]),
                "tyre_life": float(d["tyre_life"][i]),
                "speed": float(d['speed'][i]),
                "gear": int(d['gear'][i]),
                "drs": int(d['drs'][i]),
                "throttle": float(d['throttle'][i]),
                "brake": float(d['brake'][i]),
            })

        # If for some reason we have no drivers at this instant
        if not snapshot:
            continue

        # 5b. Sort by race distance to get POSITIONS (1–20)
        # Leader = largest race distance covered
        snapshot.sort(key=lambda r: (r.get("lap", 0), r["dist"]), reverse=True)

        leader = snapshot[0]
        leader_lap = leader["lap"]

        # 5c. Prepare frame data
        frame_data = {}

        for idx, car in enumerate(snapshot):
            code = car["code"]
            position = idx + 1

            #Pit stop detection
            in_pit=False
            for start,end in pit_windows_shifted.get(code,[]):
                if start<=t<=end:
                    in_pit=True
                    break
            
            # include speed, gear, drs_active in frame driver dict
            frame_data[code] = {
                "x": car["x"],
                "y": car["y"],
                "dist": car["dist"],
                "lap": car["lap"],
                "rel_dist": round(car["rel_dist"], 4),
                "tyre": car["tyre"],
                "tyre_life": car["tyre_life"],
                "position": position,
                "speed": car["speed"],
                "gear": car["gear"],
                "drs": car["drs"],
                "throttle": car["throttle"],
                "brake": car["brake"],
                "in_pit": in_pit
            }

        weather_snapshot = {}
        if weather_resampled:
            try:
                wt = weather_resampled
                rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
                weather_snapshot = {
                    "track_temp": float(wt["track_temp"][i])
                    if wt.get("track_temp") is not None
                    else None,
                    "air_temp": float(wt["air_temp"][i])
                    if wt.get("air_temp") is not None
                    else None,
                    "humidity": float(wt["humidity"][i])
                    if wt.get("humidity") is not None
                    else None,
                    "wind_speed": float(wt["wind_speed"][i])
                    if wt.get("wind_speed") is not None
                    else None,
                    "wind_direction": float(wt["wind_direction"][i])
                    if wt.get("wind_direction") is not None
                    else None,
                    "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
                }
            except Exception as e:
                print(f"Failed to attach weather data to frame {i}: {e}")

        frame_payload = {
            "t": round(t, 3),
            "lap": leader_lap,  # leader's lap at this time
            "drivers": frame_data,
        }
        if weather_snapshot:
            frame_payload["weather"] = weather_snapshot

        frames.append(frame_payload)

    # 5d. Compute Safety Car positions for each frame
    compute_safety_car_positions(frames, formatted_track_statuses, session)
    report(1.0, "Telemetry ready")
    print("completed telemetry extraction...")
    print("Saving to cache file...")
    # If computed_data/ directory doesn't exist, create it
    if not os.path.exists("computed_data"):
        os.makedirs("computed_data")

    # Save using pickle (10-100x faster than JSON)
    with open(f"computed_data/{event_name}_{cache_suffix}_telemetry.pkl", "wb") as f:
        pickle.dump({
            "frames": frames,
            "driver_colors": get_driver_colors(session),
            "track_statuses": formatted_track_statuses,
            "race_control_messages": formatted_rc_messages,
            "total_laps": int(max_lap_number),
            "max_tyre_life": max_tyre_life_map,
        }, f, protocol=pickle.HIGHEST_PROTOCOL)

    print("Saved Successfully!")
    print("The replay should begin in a new window shortly")
    return {
        "frames": frames,
        "driver_colors": get_driver_colors(session),
        "track_statuses": formatted_track_statuses,
        "race_control_messages": formatted_rc_messages,
        "total_laps": int(max_lap_number),
        "max_tyre_life": max_tyre_life_map,
    }
