"""Train all three models in one go.

    python -m app.ml.train_all

Takes a few seconds on a laptop. Every model has a non-ML fallback (§33), so a
failure here degrades the demo's fidelity but never its availability.
"""

from __future__ import annotations

from app.ml import train_forecast, train_maintenance, train_spoilage
from app.ml.registry import reset_cache


def main() -> int:
    for name, module in (
        ("forecast", train_forecast),
        ("maintenance", train_maintenance),
        ("spoilage", train_spoilage),
    ):
        print(f"\n=== training: {name} ===")
        module.main()
    reset_cache()
    print("\nAll models trained.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
