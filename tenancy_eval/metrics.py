
import math
from collections import Counter

def _tokenize(text):
    # simple whitespace tokenizer + lowercase
    if text is None:
        return []
    return [t for t in text.lower().split() if t.strip()]

def _ngrams(tokens, n):
    return [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)] if len(tokens) >= n else []

def _precision_recall_f1(overlap, pred_total, ref_total):
    p = overlap / pred_total if pred_total > 0 else 0.0
    r = overlap / ref_total if ref_total > 0 else 0.0
    f1 = (2*p*r)/(p+r) if (p+r) > 0 else 0.0
    return p, r, f1

def rouge_n(ref, pred, n=1):
    ref_t = _tokenize(ref)
    pred_t = _tokenize(pred)
    ref_ngrams = Counter(_ngrams(ref_t, n))
    pred_ngrams = Counter(_ngrams(pred_t, n))
    overlap = 0
    for ng, c in pred_ngrams.items():
        overlap += min(c, ref_ngrams.get(ng, 0))
    p, r, f1 = _precision_recall_f1(overlap, sum(pred_ngrams.values()), sum(ref_ngrams.values()))
    return {"precision": p, "recall": r, "f1": f1}

def _lcs_length(xs, ys):
    # dynamic programming LCS length
    m, n = len(xs), len(ys)
    dp = [0] * (n+1)
    for i in range(1, m+1):
        prev = 0
        for j in range(1, n+1):
            tmp = dp[j]
            if xs[i-1] == ys[j-1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j-1])
            prev = tmp
    return dp[n]

def rouge_l_f1(ref, pred):
    ref_t = _tokenize(ref)
    pred_t = _tokenize(pred)
    lcs = _lcs_length(ref_t, pred_t)
    p = lcs / len(pred_t) if len(pred_t) > 0 else 0.0
    r = lcs / len(ref_t) if len(ref_t) > 0 else 0.0
    f1 = (2*p*r)/(p+r) if (p+r) > 0 else 0.0
    return {"precision": p, "recall": r, "f1": f1}
