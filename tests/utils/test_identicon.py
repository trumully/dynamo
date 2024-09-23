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

    assert color.is_similar(color)


@given(seed=st.integers(min_value=1))
def test_get_colors(seed: int) -> None:
    fg, bg = dynamo.utils.identicon.get_colors(seed)
    assert all(0 <= c <= 255 for c in fg.as_tuple())
    assert all(0 <= c <= 255 for c in bg.as_tuple())
    perceived, euclidean = fg.perceived_distance(bg), fg.euclidean_distance(bg)
    assert not fg.is_similar(bg), f"fg and bg are too similar: {fg} and {bg}\np|e = {perceived}|{euclidean}"


@given(size=st.integers(1, 100), fg=rgb(), bg=rgb(), fg_weight=st.floats(0.0, 1.0), seed=st.integers(1))
def test_identicon(
    size: int, fg: dynamo.utils.identicon.RGB, bg: dynamo.utils.identicon.RGB, fg_weight: float, seed: int
) -> None:
    identicon = dynamo.utils.identicon.Identicon(size, fg, bg, fg_weight, seed)

    assert identicon.size == size
    assert identicon.fg == fg
    assert identicon.bg == bg
    assert identicon.fg_weight == fg_weight
    assert identicon.seed == seed

    icon = identicon.icon
    assert isinstance(icon, np.ndarray)
    assert icon.shape == (size * 2, size * 2, 3)

    # Assert immutability
    with pytest.raises(AttributeError):
        identicon.size = size + 1
    with pytest.raises(AttributeError):
        identicon.fg = dynamo.utils.identicon.RGB(0, 0, 0)
    with pytest.raises(AttributeError):
        identicon.bg = dynamo.utils.identicon.RGB(255, 255, 255)
    with pytest.raises(AttributeError):
        identicon.fg_weight = 0.5
    with pytest.raises(AttributeError):
        identicon.seed = seed + 1


@given(
    color_a=rgb(),
    color_b=rgb(),
)
def test_color_distance(color_a: dynamo.utils.identicon.RGB, color_b: dynamo.utils.identicon.RGB) -> None:
    distance = color_a.perceived_distance(color_b)
    assert isinstance(distance, float)
    assert distance >= 0
