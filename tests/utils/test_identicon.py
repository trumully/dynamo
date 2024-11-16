from hypothesis import given
from hypothesis import strategies as st

from dynamo.utils import identicon
from dynamo.utils.color import RGB


@st.composite
def rgb(draw: st.DrawFn) -> RGB:
    return RGB(*draw(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255))))


@given(c=rgb())
def test_rgb_class(c: RGB) -> None:
    assert all(0 <= v <= 255 for v in c)

    assert c.is_similar_to(c)


@given(seed=st.integers(min_value=1))
def test_get_colors(seed: int) -> None:
    fg, bg = identicon.get_colors(seed)
    assert all(0 <= c <= 255 for c in fg)
    assert all(0 <= c <= 255 for c in bg)
    perceived, euclidean = (
        fg.perceived_distance_from(bg),
        fg.euclidean_distance_from(bg),
    )
    assert not fg.is_similar_to(bg), f"fg and bg are too similar: {fg} and {bg}\np|e = {perceived}|{euclidean}"


@given(c1=rgb(), c2=rgb())
def test_color_distance(c1: RGB, c2: RGB) -> None:
    distance = c1.perceived_distance_from(c2)
    assert isinstance(distance, float)
    assert distance >= 0
