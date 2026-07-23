import os

import fastf1
import fastf1.plotting

from src.lib.settings import get_settings


def enable_cache():
    """Create the configured FastF1 cache directory and activate it for session loads."""
    settings = get_settings()
    cache_path = settings.cache_location

    if not os.path.exists(cache_path):
        os.makedirs(cache_path)

    fastf1.Cache.enable_cache(cache_path)


def load_session(year, round_number, session_type="R"):
    """Load a FastF1 session with telemetry and weather channels enabled."""
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, weather=True)
    return session


def get_driver_colors(session):
    """Return FastF1 driver palette entries as RGB tuples keyed by driver code."""
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)

    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors


def get_circuit_rotation(session):
    """Read the circuit rotation angle from a loaded FastF1 session."""
    circuit = session.get_circuit_info()
    return circuit.rotation
