from hypothesis import given
from hypothesis import strategies as st

from dynamo.utils import color, identicon


@st.composite
def rgb(draw: st.DrawFn) -> color.RGB:
    return draw(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255)))


@given(some_color=rgb())
def test_rgb_class(some_color: color.RGB) -> None:
    r, g, b = some_color
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255

    assert color.color_is_similar(some_color, some_color)


@given(seed=st.integers(min_value=1))
def test_get_colors(seed: int) -> None:
    fg, bg = identicon.get_colors(seed)
    assert all(0 <= c <= 255 for c in fg)
    assert all(0 <= c <= 255 for c in bg)
    perceived, euclidean = (
        color.perceived_distance(fg, bg),
        color.euclidean_distance(fg, bg),
    )
    assert not color.color_is_similar(
        fg, bg
    ), f"fg and bg are too similar: {fg} and {bg}\np|e = {perceived}|{euclidean}"


@given(color_a=rgb(), color_b=rgb())
def test_color_distance(color_a: color.RGB, color_b: color.RGB) -> None:
    distance = color.perceived_distance(color_a, color_b)
    assert isinstance(distance, float)
    assert distance >= 0
