import importlib

import pytest


MODULES = [
    "src.data.cache_session",
    "src.data.race_telemetry",
    "src.data.safety_car",
    "src.intelligence.battery_deployment",
    "src.intelligence.battery_rl_environment",
    "src.intelligence.race_intelligence",
    "src.intelligence.strategy_flow",
    "src.lib.season",
    "src.lib.settings",
    "src.lib.time",
    "src.lib.tyres",
    "src.server.replay",
    "src.server.app",
]

OPTIONAL_DEPENDENCIES = {
    "fastf1",
    "numpy",
    "pandas",
    "scipy",
    "fastapi",
}


@pytest.mark.parametrize("module_name", MODULES)
def test_project_modules_are_importable(module_name):
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing_dependency = exc.name.split(".")[0]

        if missing_dependency in OPTIONAL_DEPENDENCIES:
            pytest.skip(f"optional dependency not installed: {missing_dependency}")

        raise
