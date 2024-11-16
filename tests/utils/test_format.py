import hypothesis.strategies as st
from hypothesis import assume, given

from dynamo.utils import format as dynamo_format


@given(
    seq=st.lists(st.text(min_size=1, max_size=10)),
    conjunction=st.text(min_size=1, max_size=10),
    oxford_comma=st.booleans(),
)
def test_human_join(seq: list[str], conjunction: str, oxford_comma: bool) -> None:
    """Test the human_join function"""
    assume(not [s for s in seq if s == conjunction])

    result = dynamo_format.human_join(seq, conjunction=conjunction, oxford_comma=oxford_comma)
    assert isinstance(result, str)

    if len(seq) == 0:
        assert not result
    elif len(seq) == 1:
        assert result == seq[0]
    elif len(seq) == 2:
        assert result == f"{seq[0]} {conjunction} {seq[1]}"
    else:
        assert result == f"{", ".join(seq[:-1])}{", " if oxford_comma else " "}{conjunction} {seq[-1]}"


@given(string=st.text(min_size=1, max_size=10))
def test_human_join_str(string: str) -> None:
    """Test the human_join function with a single string"""
    assert dynamo_format.human_join(string) == string
