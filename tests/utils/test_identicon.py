import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

import dynamo.utils.identicon


@st.composite
def rgb(draw: st.DrawFn) -> dynamo.utils.identicon.RGB:
    values = draw(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255)))
    return dynamo.utils.identicon.RGB(*values)


@given(color=rgb())
def test_rgb_class(color: dynamo.utils.identicon.RGB) -> None:
    assert 0 <= color.r <= 255
    assert 0 <= color.g <= 255
    assert 0 <= color.b <= 255
    assert color.as_tuple() == (color.r, color.g, color.b)


@given(st.integers(min_value=1))
def test_make_color(seed: int) -> None:
    color = dynamo.utils.identicon.make_color(seed)
    assert isinstance(color, dynamo.utils.identicon.RGB)
    assert 0 <= color.r <= 255
    assert 0 <= color.g <= 255
    assert 0 <= color.b <= 255


@given(st.integers(min_value=1))
def test_get_colors(seed: int) -> None:
    fg, bg = dynamo.utils.identicon.get_colors(seed=seed)
    assert isinstance(fg, dynamo.utils.identicon.RGB)
    assert isinstance(bg, dynamo.utils.identicon.RGB)
    assert fg.as_tuple() != bg.as_tuple()


@given(color=rgb())
def test_rgb_as_hex(color: dynamo.utils.identicon.RGB) -> None:
    hex_color = dynamo.utils.identicon.rgb_as_hex(color)
    assert hex_color.startswith("#")
    assert len(hex_color) == 7
    assert all(c in "0123456789abcdef" for c in hex_color[1:])


@given(
    size=st.integers(min_value=1, max_value=100),
    fg=rgb(),
    bg=rgb(),
    fg_weight=st.floats(min_value=0, max_value=1),
    seed=st.integers(min_value=1),
)
def test_identicon(
    size: int, fg: dynamo.utils.identicon.RGB, bg: dynamo.utils.identicon.RGB, fg_weight: float, seed: int
) -> None:
    identicon = dynamo.utils.identicon.Identicon(size, fg, bg, fg_weight, seed)

    assert identicon.size == size
    assert identicon.fg == fg
    assert identicon.bg == bg
    assert identicon.fg_weight == fg_weight
    assert identicon.seed == seed

    pattern = identicon.pattern
    assert isinstance(pattern, np.ndarray)
    assert pattern.shape == (size * 2, size)

    icon = identicon.icon
    assert isinstance(icon, np.ndarray)
    assert icon.shape == (size * 2, size * 2, 3)


@given(
    color_a=rgb(),
    color_b=rgb(),
)
def test_color_distance(color_a: dynamo.utils.identicon.RGB, color_b: dynamo.utils.identicon.RGB) -> None:
    distance = dynamo.utils.identicon.color_distance(color_a, color_b)
    assert isinstance(distance, float)
    assert distance >= 0


@pytest.mark.parametrize(
    "r,g,b,expected",
    [
        (0, 0, 0, "#000000"),
        (255, 255, 255, "#ffffff"),
        (128, 128, 128, "#808080"),
    ],
)
def test_rgb_as_hex_specific(r: int, g: int, b: int, expected: str) -> None:
    rgb = dynamo.utils.identicon.RGB(r, g, b)
    assert dynamo.utils.identicon.rgb_as_hex(rgb) == expected
