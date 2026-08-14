"""Benchmark runner: pipeline vs naive baseline on the labelled eval set.

    uv run python -m app.eval.run --labels ../eval/labels.json --images ../eval/images

Writes a markdown report with the recall/precision table and an explicit Gate 1
verdict. Real model calls throughout — there is nothing to mock and nothing worth
mocking (AGENTS.md).
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.agents import prompts
from app.agents.pipeline import ImageReport, process_image
from app.domain.grid import Grid
from app.eval.baseline import run_baseline
from app.eval.dataset import LabelledImage, load_labels, summarise
from app.eval.scoring import TABLE_HEADER, Metrics, gate_1_verdict, match_defects
from app.imaging.canvas import load


async def _score_one(
    entry: LabelledImage,
    image_dir: Path,
    guidelines: str,
    pipeline_metrics: Metrics,
    baseline_metrics: Metrics,
    verbose: bool,
) -> dict:
    image = load(image_dir / entry.image)
    grid = Grid.for_image(image.width, image.height)
    truth = [defect.cells for defect in entry.defects]

    started = time.monotonic()
    baseline_result = await run_baseline(image, guidelines, grid)
    baseline_seconds = time.monotonic() - started
    baseline_cells = [suspect.cells for suspect in baseline_result.suspects]

    started = time.monotonic()
    report: ImageReport = await process_image(image, guidelines, grid=grid)
    pipeline_seconds = time.monotonic() - started
    pipeline_cells = [defect.cells for defect in report.defects]

    baseline_match = match_defects(baseline_cells, truth)
    pipeline_match = match_defects(pipeline_cells, truth)

    baseline_metrics.add(baseline_match, is_clean=entry.is_clean, seconds=baseline_seconds)
    pipeline_metrics.add(pipeline_match, is_clean=entry.is_clean, seconds=pipeline_seconds)

    if verbose:
        print(
            f"  {entry.image:<28} truth={len(truth):<2} "
            f"baseline={baseline_match.true_positives}/{len(baseline_cells)} "
            f"pipeline={pipeline_match.true_positives}/{len(pipeline_cells)} "
            f"({pipeline_seconds:.0f}s)"
        )

    return {
        "image": entry.image,
        "truth": len(truth),
        "baseline_found": baseline_match.true_positives,
        "baseline_reported": len(baseline_cells),
        "pipeline_found": pipeline_match.true_positives,
        "pipeline_reported": len(pipeline_cells),
        "pipeline_dismissed": len(report.dismissals),
        "pipeline_seconds": round(pipeline_seconds, 1),
        "pro_gate_ran": report.pro_gate_ran,
    }


async def main(labels_path: Path, image_dir: Path, out_dir: Path, verbose: bool) -> int:
    labels = load_labels(labels_path)
    composition = summarise(labels)
    guidelines = prompts.built_in_guideline()

    print(
        f"eval set: {composition['images']} images "
        f"({composition['clean_images']} clean), {composition['defects']} labelled defects"
    )

    pipeline_metrics, baseline_metrics = Metrics(), Metrics()
    per_image = []

    # Sequential on purpose: concurrent runs would make the latency figures meaningless.
    for entry in labels:
        try:
            per_image.append(
                await _score_one(
                    entry, image_dir, guidelines, pipeline_metrics, baseline_metrics, verbose
                )
            )
        except Exception as exc:  # noqa: BLE001 — one bad image must not lose the run
            print(f"  {entry.image}: FAILED ({exc})")

    verdict = gate_1_verdict(pipeline_metrics, baseline_metrics)
    report = _render(composition, pipeline_metrics, baseline_metrics, verdict, per_image)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "benchmark.md").write_text(report, encoding="utf-8")
    (out_dir / "benchmark.json").write_text(
        json.dumps(
            {
                "composition": composition,
                "pipeline": _metrics_dict(pipeline_metrics),
                "baseline": _metrics_dict(baseline_metrics),
                "gate_1": [
                    {"check": name, "passed": passed, "value": value}
                    for name, passed, value in verdict
                ],
                "per_image": per_image,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n" + report)
    print(f"written to {out_dir / 'benchmark.md'}")
    return 0 if all(passed for _, passed, _ in verdict) else 1


def _metrics_dict(metrics: Metrics) -> dict:
    return {
        "recall": round(metrics.recall, 3),
        "precision": round(metrics.precision, 3),
        "f1": round(metrics.f1, 3),
        "true_positives": metrics.true_positives,
        "false_positives": metrics.false_positives,
        "false_negatives": metrics.false_negatives,
        "false_positives_per_clean_image": round(metrics.false_positives_per_clean_image, 2),
        "seconds_per_image": round(metrics.seconds_per_image, 1),
    }


def _render(composition, pipeline, baseline, verdict, per_image) -> str:
    lift = (pipeline.recall - baseline.recall) * 100
    lines = [
        "# Benchmark: pipeline vs naive baseline",
        "",
        f"Eval set: **{composition['images']} images** "
        f"({composition['clean_images']} clean), "
        f"**{composition['defects']} labelled defects**.",
        "",
        TABLE_HEADER,
        baseline.as_row("naive single prompt"),
        pipeline.as_row("**multi-agent pipeline**"),
        "",
        f"Recall lift: **{lift:+.1f} points**.",
        "",
        "### Reading these numbers",
        "",
        "**Precision is a lower bound.** Anything the pipeline finds that is not in "
        "`labels.json` counts as a false positive, including real defects nobody "
        "labelled. Unless the labels are exhaustive — every defect in every image, not "
        "just the obvious ones — the true precision is higher than the figure above.",
        "",
        f"**The false-positive rate on clean images is the trustworthy signal**: those "
        f"{composition['clean_images']} images have complete ground truth, because there "
        f"is nothing in them to find. Any finding there is unambiguously wrong.",
        "",
        f"**Sample size.** With {composition['defects']} labelled defects, one defect is "
        f"worth {100 / max(composition['defects'], 1):.1f} recall points, so the recall "
        "lift cannot resolve differences finer than that. Treat a lift within one "
        "defect of the threshold as undecided, not as a pass or a fail.",
        "",
        "## Gate 1",
        "",
        "| Check | Result | Value |",
        "| --- | --- | --- |",
    ]
    lines += [
        f"| {name} | {'PASS' if passed else 'FAIL'} | {value} |" for name, passed, value in verdict
    ]

    lines += [
        "",
        "## Per image",
        "",
        "| Image | Truth | Baseline found | Pipeline found | Dismissed | Time |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines += [
        f"| {row['image']} | {row['truth']} | "
        f"{row['baseline_found']}/{row['baseline_reported']} | "
        f"{row['pipeline_found']}/{row['pipeline_reported']} | "
        f"{row['pipeline_dismissed']} | {row['pipeline_seconds']}s |"
        for row in per_image
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("../eval/labels.json"))
    parser.add_argument("--images", type=Path, default=Path("../eval/images"))
    parser.add_argument("--out", type=Path, default=Path("../eval/output"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    raise SystemExit(asyncio.run(main(args.labels, args.images, args.out, not args.quiet)))
