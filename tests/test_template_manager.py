import pytest

from src.gridgpt.template_manager import select_template


def test_templates_load(templates):
    assert len(templates) >= 3
    ids = [t["id"] for t in templates]
    assert len(ids) == len(set(ids)), "template ids must be unique"


def test_select_template_by_id(templates):
    template_id = templates[0]["id"]
    template = select_template(template_id=template_id)
    assert template["id"] == template_id


def test_select_unknown_template_raises():
    with pytest.raises(ValueError):
        select_template(template_id="does_not_exist")


def test_template_structure_is_consistent(templates):
    """Every slot must match the grid: cells in bounds, open, and contiguous."""
    for template in templates:
        grid = template["grid"]
        n_rows, n_cols = len(grid), len(grid[0])
        covered_cells = set()

        for slot in template["slots"]:
            cells = [tuple(cell) for cell in slot["cells"]]
            assert len(cells) == slot["length"], f"{template['id']}/{slot['id']}: length mismatch"
            assert tuple(slot["start"]) == cells[0], f"{template['id']}/{slot['id']}: start mismatch"

            for row, col in cells:
                assert 0 <= row < n_rows and 0 <= col < n_cols
                assert grid[row][col] != "#", f"{template['id']}/{slot['id']}: cell on blocked square"
                covered_cells.add((row, col))

            # Cells must be consecutive in the slot's direction
            for (r1, c1), (r2, c2) in zip(cells, cells[1:]):
                if slot["direction"] == "across":
                    assert (r2, c2) == (r1, c1 + 1)
                else:
                    assert (r2, c2) == (r1 + 1, c1)

        # Every open cell must be covered by at least one slot
        for row in range(n_rows):
            for col in range(n_cols):
                if grid[row][col] != "#":
                    assert (row, col) in covered_cells, f"{template['id']}: uncovered cell {(row, col)}"


def test_theme_slots_exist(templates):
    for template in templates:
        slot_ids = {slot["id"] for slot in template["slots"]}
        for theme_slot_id in template.get("theme_slots", []):
            assert theme_slot_id in slot_ids
