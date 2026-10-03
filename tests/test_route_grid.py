import numpy as np

from arctic_passage_atlas.route_grid import BBOX, DLAT, DLON, grid_shape, rasterize_land


def _square(west, south, east, north):
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [
        [[west, south], [east, south], [east, north], [west, north], [west, south]]]}}


def test_grid_shape_matches_bbox_and_spacing():
    rows, cols = grid_shape()
    assert rows == round((BBOX[3] - BBOX[1]) / DLAT) and cols == round((BBOX[2] - BBOX[0]) / DLON)


def test_land_polygon_lands_in_the_right_cells_and_row_zero_is_north():
    land = rasterize_land({"features": [_square(-100.0, 70.0, -99.0, 71.0)]})
    r_n = int((BBOX[3] - 70.5) / DLAT)
    c_w = int((-99.5 - BBOX[0]) / DLON)
    assert land[r_n, c_w]                      # inside the square
    assert not land[r_n, c_w + 100]            # 5 degrees east of it
    assert not land[0, 0] and land.sum() > 0
    # 1 degree x 1 degree is 20 x 50 cells (give or take the polygon edge)
    assert abs(int(land.sum()) - 20 * 50 * 1) <= 120


def test_holes_are_ignored_so_lakes_count_as_land():
    outer = [[-100, 70], [-98, 70], [-98, 72], [-100, 72], [-100, 70]]
    hole = [[-99.5, 70.5], [-98.5, 70.5], [-98.5, 71.5], [-99.5, 71.5], [-99.5, 70.5]]
    land = rasterize_land({"features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [outer, hole]}}]})
    r = int((BBOX[3] - 71.0) / DLAT); c = int((-99.0 - BBOX[0]) / DLON)
    assert land[r, c]                          # the hole's centre is still land


def test_features_outside_the_grid_are_skipped():
    land = rasterize_land({"features": [_square(10.0, 10.0, 20.0, 20.0)]})
    assert isinstance(land, np.ndarray) and land.sum() == 0
