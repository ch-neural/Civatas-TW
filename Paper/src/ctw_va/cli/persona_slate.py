"""CLI: civatas-exp persona-slate ..."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import click

from ..persona import slate_builder


@click.group("persona-slate")
def persona_slate():
    """Persona slate management (Phase A3)."""
    pass


@persona_slate.command("export")
@click.option("--output", type=click.Path(), required=True,
              help="Output JSONL path.")
@click.option("--n", type=int, default=300, show_default=True,
              help="Number of personas.")
@click.option("--seed", type=int, default=20240113, show_default=True,
              help="Replication seed (deterministic).")
def export_cmd(output, n, seed):
    """A3: export deterministic persona slate."""
    personas = slate_builder.build_slate(n=n, seed=seed)
    result = slate_builder.write_slate_jsonl(personas, output)
    click.echo(f"✅ Slate exported: {result['path']}")
    click.echo(f"   count: {result['count']}")
    click.echo(f"   slate_id: {result['slate_id']}")
    click.echo(f"   sha256: {result['sha256']}")


@persona_slate.command("verify")
@click.argument("slate_path", type=click.Path(exists=True))
def verify_cmd(slate_path):
    """Check marginal distributions against spec tolerances."""
    personas_raw = [
        json.loads(l)
        for l in Path(slate_path).read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    n = len(personas_raw)
    click.echo(f"N = {n}")
    click.echo()

    def _report(dim, observed_counts, targets, tolerance_pp):
        click.echo(f"{dim} (tolerance ±{tolerance_pp*100:.0f}pp):")
        ok = True
        for k, target in sorted(targets.items(), key=lambda x: -x[1]):
            obs_c = observed_counts.get(k, 0)
            obs_p = obs_c / n
            delta = obs_p - target
            mark = "✅" if abs(delta) <= tolerance_pp else "❌"
            if abs(delta) > tolerance_pp:
                ok = False
            click.echo(f"  {mark} {k}: {obs_c}/{n}={obs_p:.1%} "
                       f"(target {target:.1%}, Δ{delta:+.1%})")
        click.echo()
        return ok

    pl = Counter(p["party_lean"] for p in personas_raw)
    a = _report("party_lean (5-bucket)", pl, slate_builder.PARTY_LEAN_5_RATIOS, 0.02)

    eth = Counter(p["ethnicity"] for p in personas_raw)
    b = _report("ethnicity", eth, slate_builder.ETHNICITY_RATIOS, 0.01)

    click.echo("Overall:" + (" ✅ within tolerance" if (a and b) else " ❌ out of tolerance"))


@persona_slate.command("inspect")
@click.argument("persona_id")
@click.option("--slate", type=click.Path(exists=True), required=True)
def inspect_cmd(persona_id, slate):
    """Print full persona record by persona_id."""
    for line in Path(slate).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        if p.get("person_id") == persona_id:
            click.echo(json.dumps(p, ensure_ascii=False, indent=2))
            return
    click.echo(f"❌ {persona_id} not found in {slate}")
