import json
import pytest
from edge_rpg.geo import Safety, polygons


def rectangle(left, bottom, right, top):
    return [[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]


def safety(allowed, blocked=()):
    fence = Safety.__new__(Safety)
    fence.allow_unlisted = False
    fence.allowed = allowed
    fence.blocked = blocked
    return fence


def test_submetre_blocked_strip_cannot_fall_between_samples():
    # ~11 m trajectory with a 1 cm-wide prohibited strip between metre samples.
    fence = safety([[rectangle(120, 24, 121, 25)]],
                   [[rectangle(120.0000433, 24.49, 120.0000434, 24.51)]])
    a, b = (24.5, 120.0), (24.5, 120.0001)
    assert fence.permits(*a) and fence.permits(*b)
    assert not fence.permits_segment(a, b)
    assert not fence.permits_segment(b, a)


def test_allowed_polygon_hole_cannot_be_crossed():
    fence = safety([[rectangle(0, 0, 10, 10), rectangle(4, 4, 6, 6)]])
    assert not fence.permits_segment((5, 2), (5, 8))
    assert fence.permits_segment((2, 2), (2, 8))


def test_overlapping_allowed_polygons_are_a_union():
    fence = safety([[rectangle(0, 0, 6, 10)], [rectangle(4, 0, 10, 10)]])
    assert fence.permits_segment((5, 2), (5, 8))


def test_gap_between_allowed_polygons_is_rejected():
    fence = safety([[rectangle(0, 0, 4, 10)], [rectangle(4.000001, 0, 10, 10)]])
    assert not fence.permits_segment((5, 2), (5, 8))


def test_blocked_boundary_tangent_is_rejected():
    fence = safety([[rectangle(0, 0, 10, 10)]], [[rectangle(4, 4, 6, 6)]])
    assert not fence.permits_segment((4, 2), (4, 8))
    assert fence.permits_segment((3, 2), (3, 8))


def test_stationary_points_and_blocked_hole():
    fence = safety([[rectangle(0, 0, 10, 10)]],
                   [[rectangle(2, 2, 8, 8), rectangle(4, 4, 6, 6)]])
    assert fence.permits_segment((5, 5), (5, 5))
    assert fence.permits_segment((4.5, 4.5), (5.5, 5.5))
    assert not fence.permits_segment((3, 3), (3, 3))


@pytest.mark.parametrize('value', [float('nan'), float('inf'), True, 181])
def test_invalid_geofence_coordinate_fails_closed(tmp_path, value):
    ring = rectangle(120, 24, 121, 25)
    ring[1][0] = value
    path = tmp_path/'invalid.geojson'
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Polygon', 'coordinates': [ring]}}
    ]}))
    with pytest.raises(ValueError):
        polygons(path)
