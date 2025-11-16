import json, argparse
from collections import defaultdict
from pathlib import Path
from metrics import rouge_n, rouge_l_f1

def safe_get(d, k, default=None):
    v = d.get(k, default)
    return v if v is not None else default

def evaluate(test_path, pred_path, out_md_path, per_item_csv_path=None):
    tests = [json.loads(l) for l in Path(test_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    preds = {}
    for l in Path(pred_path).read_text(encoding="utf-8").splitlines():
        if not l.strip(): 
            continue
        j = json.loads(l)
        preds[j["id"]] = j

    bucket_scores = defaultdict(list)
    overall_r1 = []; overall_r2 = []; overall_rl = []
    per_item = []

    for t in tests:
        tid = t["id"]
        ref = t["reference_answer"]
        diff = safe_get(t, "difficulty", "unknown")
        topic = safe_get(t, "topic", "unknown")
        bkey = (diff, topic)
        pred = preds.get(tid, {}).get("model_answer", "")

        r1 = rouge_n(ref, pred, n=1)["f1"]
        r2 = rouge_n(ref, pred, n=2)["f1"]
        rl = rouge_l_f1(ref, pred)["f1"]

        overall_r1.append(r1); overall_r2.append(r2); overall_rl.append(rl)
        bucket_scores[bkey].append(rl)

        per_item.append({
            "id": tid, "difficulty": diff, "topic": topic,
            "rouge1_f1": r1, "rouge2_f1": r2, "rougeL_f1": rl
        })

    if per_item_csv_path and per_item:
        import csv
        fieldnames = ["id","difficulty","topic","rouge1_f1","rouge2_f1","rougeL_f1"]
        with open(per_item_csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader(); w.writerows(per_item)

    def mean_safe(xs): return sum(xs)/len(xs) if xs else 0.0
    rl_sorted = sorted(overall_rl)
    p10 = rl_sorted[int(0.1*len(rl_sorted))] if rl_sorted else 0.0
    p90 = rl_sorted[int(0.9*len(rl_sorted))-1] if rl_sorted else 0.0

    overall = {
        "count": len(per_item),
        "rouge1_mean": mean_safe(overall_r1),
        "rouge2_mean": mean_safe(overall_r2),
        "rougeL_mean": mean_safe(overall_rl),
        "rougeL_p10": p10,
        "rougeL_p90": p90,
    }

    lines = []
    lines.append("# Evaluation Report\n")
    lines.append(f"- Total items: **{overall['count']}**")
    lines.append(f"- ROUGE-1(F1) mean: **{overall['rouge1_mean']:.3f}**")
    lines.append(f"- ROUGE-2(F1) mean: **{overall['rouge2_mean']:.3f}**")
    lines.append(f"- ROUGE-L(F1) mean: **{overall['rougeL_mean']:.3f}**")
    lines.append(f"- ROUGE-L P10 / P90: **{overall['rougeL_p10']:.3f} / {overall['rougeL_p90']:.3f}**\n")

    lines.append("## Buckets (difficulty × topic)\n")
    lines.append("| difficulty | topic | count | ROUGE-L mean |")
    lines.append("|---|---:|---:|---:|")
    for (diff, topic), vals in sorted(bucket_scores.items()):
        cnt = len(vals)
        rl_mean = (sum(vals)/cnt) if cnt else 0.0
        lines.append(f"| {diff} | {topic} | {cnt} | {rl_mean:.3f} |")

    lines.append("\n---\n")
    lines.append("**Notes**:\n- ROUGE implemented locally (no external packages).\n")

    Path(out_md_path).write_text("\n".join(lines), encoding="utf-8")
    return out_md_path

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True, help="path to test.jsonl")
    ap.add_argument("--pred", required=True, help="path to preds.jsonl")
    ap.add_argument("--out", default="eval_report.md", help="output markdown report")
    ap.add_argument("--per_item_csv", default=None, help="optional CSV of per-item metrics")
    args = ap.parse_args()
    out = evaluate(args.test, args.pred, args.out, args.per_item_csv)
    print(f"Report written to: {out}")