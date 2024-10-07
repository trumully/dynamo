from hypothesis import given
from hypothesis import strategies as st

from dynamo.utils import identicon


@st.composite
def rgb(draw: st.DrawFn) -> identicon.RGB:
    return draw(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255)))


@given(color=rgb())
def test_rgb_class(color: identicon.RGB) -> None:
    r, g, b = color
    assert 0 <= r <= 255
    assert 0 <= g <= 255
    assert 0 <= b <= 255

    assert identicon.color_is_similar(color, color)


@given(seed=st.integers(min_value=1))
def test_get_colors(seed: int) -> None:
    fg, bg = identicon.get_colors(seed)
    assert all(0 <= c <= 255 for c in fg)
    assert all(0 <= c <= 255 for c in bg)
    perceived, euclidean = (
        identicon.perceived_distance(fg, bg),
        identicon.euclidean_distance(fg, bg),
    )
    assert not identicon.color_is_similar(
        fg, bg
    ), f"fg and bg are too similar: {fg} and {bg}\np|e = {perceived}|{euclidean}"


@given(color_a=rgb(), color_b=rgb())
def test_color_distance(color_a: identicon.RGB, color_b: identicon.RGB) -> None:
    distance = identicon.perceived_distance(color_a, color_b)
    assert isinstance(distance, float)
    assert distance >= 0
