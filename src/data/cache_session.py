import os

import fastf1
import fastf1.plotting

from src.lib.settings import get_settings

def enable_cache():
    # Get cache location from settings
    settings = get_settings()
    cache_path = settings.cache_location

    # Check if cache folder exists
    if not os.path.exists(cache_path):
        os.makedirs(cache_path)

    # Enable local cache
    fastf1.Cache.enable_cache(cache_path)


def load_session(year, round_number, session_type="R"):
    # session_type: 'R' (Race), 'S' (Sprint) etc.
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, weather=True)
    return session


# The following functions require a loaded session object


def get_driver_colors(session):
    color_mapping = fastf1.plotting.get_driver_color_mapping(session)

    # Convert hex colors to RGB tuples
    rgb_colors = {}
    for driver, hex_color in color_mapping.items():
        hex_color = hex_color.lstrip("#")
        rgb = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        rgb_colors[driver] = rgb
    return rgb_colors


def get_circuit_rotation(session):
    circuit = session.get_circuit_info()
    return circuit.rotation
