"""Venue dialogue is authored context, not new cultural evidence or game state."""

import pytest

from backend.app.content import make_chapter
from backend.app.culture import chapter_for_state
from backend.app.models import GameState
from backend.app.presentation import resident_text


@pytest.mark.parametrize(
    ("resident", "before", "after", "expected"),
    [
        ("mara", [], ["map"], "Ivo"),
        ("ivo", [], ["map"], "Trade me"),
        ("ivo", ["map"], ["map", "rhythm"], "Sera"),
        ("sera", [], ["rhythm"], "two ribbons"),
        ("sera", ["rhythm"], ["rhythm", "chronicle", "guarding"], "letters stay sealed"),
        ("beacon", [], ["map", "rhythm", "chronicle"], "All three memories"),
    ],
)
def test_residents_respond_to_confirmed_progress_without_mutation(resident, before, after, expected):
    state = GameState(flags=after)
    snapshot = state.model_dump()
    assert resident_text(resident, GameState(flags=before)) != resident_text(resident, state)
    assert expected in resident_text(resident, state)
    assert state.model_dump() == snapshot


def test_presentational_names_preserve_saved_ids_geometry_choices_and_base():
    base = make_chapter()
    snapshot = base.model_dump()
    state = GameState(flags=["map", "rhythm"])
    dressed = chapter_for_state(base, state)
    assert "Side A" in dressed.locations[0].name
    assert "projectionist" in dressed.locations[1].objects[0].name
    for old, new in zip(base.locations, dressed.locations, strict=True):
        assert (old.id, old.rows) == (new.id, new.rows)
        assert [(o.id, o.x, o.y, [c.id for c in o.choices]) for o in old.objects] == [
            (o.id, o.x, o.y, [c.id for c in o.choices]) for o in new.objects
        ]
    assert base.model_dump() == snapshot
