import hypothesis.strategies as st
import pytest
from hypothesis import assume, given

import dynamo.utils.format


@st.composite
def text_block(draw: st.DrawFn, min_size: int, max_size: int) -> str:
    return draw(st.text(min_size=min_size, max_size=max_size))


format_spec_strategy = st.one_of(
    st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
    st.tuples(
        st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
        st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
    ).map(lambda x: f"{x[0]}|{x[1]}"),
)


@given(string=text_block(10, 100), max_len=st.integers(min_value=1, max_value=100))
def test_shorten_string(string: str, max_len: int) -> None:
    """Test the shorten_string function"""
    text = dynamo.utils.format.shorten_string(string, max_len=max_len)
    assert len(text) <= max_len + 3
    assert text.endswith("...") if len(string) > max_len else not text.endswith("...")


@given(string=text_block(50, 100), max_len=st.integers(min_value=50, max_value=100))
def test_shorten_string_long(string: str, max_len: int) -> None:
    """Test the shorten_string function with a long string"""
    text = dynamo.utils.format.shorten_string(string, max_len=max_len)
    assert len(text) <= max_len + 3
    assert text.endswith("...") if len(string) > max_len else not text.endswith("...")


@given(string=text_block(0, 0), max_len=st.integers(min_value=1, max_value=100))
def test_shorten_string_empty(string: str, max_len: int) -> None:
    """Test the shorten_string function with an empty string"""
    assert dynamo.utils.format.shorten_string(string, max_len=max_len) == "Nothing provided"


@given(value=st.integers(), format_spec=format_spec_strategy, skip_value=st.booleans())
def test_plural_format(value: int, format_spec: str, skip_value: bool) -> None:
    """Test the plural format function"""
    p = dynamo.utils.format.plural(value)
    if skip_value:
        format_spec += "!"

    result = format(p, format_spec)

    # Check basic properties
    assert isinstance(result, str)
    assert result != ""

    # Check if value is included when not skipped
    if not skip_value:
        assert str(abs(value)) in result

    # Check singular/plural logic
    singular, _, custom_plural = format_spec.rstrip("!").partition("|")
    plural_form = custom_plural or f"{singular}s"

    assert singular in result if abs(value) == 1 else plural_form in result


@given(value=st.integers())
def test_plural_value_immutable(value: int) -> None:
    """Test the plural value is immutable"""
    p = dynamo.utils.format.plural(value)
    with pytest.raises(AttributeError):
        p.value = value + 1  # type: ignore


@pytest.mark.parametrize(
    "value, format_spec, expected",
    [
        (0, "item", "0 items"),
        (1, "child|children", "1 child"),
        (-1, "item!", "item"),
        (2, "foot|feet!", "feet"),
    ],
)
def test_plural_specific_cases(value: int, format_spec: str, expected: str) -> None:
    """Test the plural format function with unique plural cases"""
    p = dynamo.utils.format.plural(value)
    assert format(p, format_spec) == expected


@given(
    seq=st.lists(st.text(min_size=1, max_size=10)),
    conjunction=st.text(min_size=1, max_size=10),
    oxford_comma=st.booleans(),
)
def test_human_join(seq: list[str], conjunction: str, oxford_comma: bool) -> None:
    """Test the human_join function"""
    assume(not [s for s in seq if s == conjunction])

    result = dynamo.utils.format.human_join(seq, conjunction=conjunction, oxford_comma=oxford_comma)
    assert isinstance(result, str)

    if len(seq) == 0:
        assert result == ""
    elif len(seq) == 1:
        assert result == seq[0]
    elif len(seq) == 2:
        assert result == f"{seq[0]} {conjunction} {seq[1]}"
    else:
        assert result == f"{', '.join(seq[:-1])}{', ' if oxford_comma else ' '}{conjunction} {seq[-1]}"
