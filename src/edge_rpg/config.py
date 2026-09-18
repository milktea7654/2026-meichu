from pathlib import Path
import math
import yaml


def load_config(path="config/game.yaml"):
    path = Path(path).resolve()
    with path.open() as f:
        cfg = yaml.safe_load(f)
    root = path.parent.parent
    for section, key in [(None, "database"), ("safety", "allowed"), ("safety", "blocked"),
                         ("ui", "tiles"), ("vision", "classifier"), ("vision", "detector"),
                         ("vision", "classifier_labels"), ("vision", "detector_labels"),
                         ("dialogue", "model")]:
        obj = cfg if section is None else cfg[section]
        obj[key] = str(root / obj[key])
    e, loc = cfg["exploration"], cfg["location"]
    if e.get('mode', 'legacy_h3') not in ('square_visits', 'legacy_h3'):
        raise ValueError('Unknown exploration mode')
    if e.get('mode') == 'square_visits':
        size, count = e.get('cell_size_m'), e.get('cells_per_event')
        if isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size) or not 5 <= size <= 1000:
            raise ValueError('cell_size_m must be between 5 and 1000 metres')
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError('cells_per_event must be a positive integer')
    if not 0 <= e["h3_resolution"] <= 15 or not 0 < e["event_threshold"] <= 1:
        raise ValueError("Invalid H3 resolution or exploration threshold")
    if len(e["weights"]) != 4 or any(x < 0 for x in e["weights"]) or not math.isclose(sum(e["weights"]), 1):
        raise ValueError("Exploration weights must be four nonnegative numbers summing to 1")
    if not 0 < loc["gps_valid_accuracy_m"] <= loc["gps_display_accuracy_m"]:
        raise ValueError("Invalid GPS accuracy thresholds")
    for key in ("dwell_target_sec", "movement_target_m", "observation_target", "max_sample_gap_sec"):
        if e[key] <= 0:
            raise ValueError(f"{key} must be positive")
    if not 0 < loc["smoothing_alpha"] <= 1 or loc["stale_sec"] <= 0:
        raise ValueError("Invalid GPS smoothing or stale interval")
    if cfg['vision']['max_saved_observations'] < e['observation_target']:
        raise ValueError('Saved observation limit must cover the observation target')
    for section, keys in {'vision': ('fps','analysis_duration_sec','retry_sec','observation_max_age_sec'),
                          'audio': ('sample_rate','silence_sec','max_segment_sec','timeout_sec'),
                          'dialogue': ('timeout_sec','max_context','max_output_tokens'),
                          'ui': ('fps','tile_cache','width','height'),
                          'location': ('speed_window_sec','max_jump_speed_mps','max_exploration_speed_mps')}.items():
        for key in keys:
            value=cfg[section][key]
            if not isinstance(value,(int,float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{section}.{key} must be finite and positive')
    if cfg['ui']['width'] < 960 or cfg['ui']['height'] < 640:
        raise ValueError('The board UI requires at least 960 x 640')
    return cfg
