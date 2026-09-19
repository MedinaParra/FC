import numpy as np
import pandas as pd
import pytest

from kinofm_v4 import (
    EXPECTED, K, N, cross_markov, global_freq, self_markov,
    top14, to_binary, validate_numbers, walk_forward,
)


def synthetic_df(n=40, seed=123):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(n):
        nums = sorted((rng.choice(np.arange(1, 26), 14, replace=False)).tolist())
        rows.append([1000+s, f"2020-01-{(s%28)+1:02d}", *nums])
    return pd.DataFrame(rows, columns=['sorteo','fecha',*[f'n{i}' for i in range(1,15)]])


def test_constants():
    assert N == 25
    assert K == 14
    assert EXPECTED == pytest.approx(7.84)


def test_validate_numbers():
    assert validate_numbers(range(1, 15)) == list(range(1, 15))
    with pytest.raises(ValueError): validate_numbers([1]*14)
    with pytest.raises(ValueError): validate_numbers(list(range(1,14)) + [26])


def test_binary_rows_sum_14():
    y = to_binary(synthetic_df())
    assert y.shape == (40, 25)
    assert np.all(y.sum(axis=1) == 14)


def test_top14_returns_unique_indices():
    sel = top14(np.arange(25, dtype=float))
    assert len(sel) == 14
    assert len(set(sel.tolist())) == 14
    assert sel.min() >= 0 and sel.max() < 25


def test_markov_score_shapes():
    y = to_binary(synthetic_df(60))
    assert self_markov(y).shape == (25,)
    assert cross_markov(y).shape == (25,)


def test_walk_forward_causal_smoke():
    y = to_binary(synthetic_df(80))
    r = walk_forward(y, global_freq, start=40)
    assert r['n'] == 40
    assert 3 <= r['mean_hits'] <= 14
