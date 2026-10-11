import argparse
import json

import evaluate_strategy_b6_gate as gate


PRIMARY = "B61_SHORT_EXPANSION_ACCEPTANCE"
NEIGHBOR = "B61_SHORT_EXPANSION_ACCEPTANCE_NEIGHBOR"


def evaluate(recent, prior, holdout=None):
    original_primary = gate.PRIMARY
    original_neighbor = gate.NEIGHBOR
    gate.PRIMARY = PRIMARY
    gate.NEIGHBOR = NEIGHBOR
    try:
        return gate.evaluate(
            recent,
            prior,
            holdout,
            require_long=False,
        )
    finally:
        gate.PRIMARY = original_primary
        gate.NEIGHBOR = original_neighbor


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Strategy B6.1 promotion gate"
    )
    parser.add_argument("--development-recent", required=True)
    parser.add_argument("--development-prior", required=True)
    parser.add_argument("--holdout")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        gate.read_json(args.development_recent),
        gate.read_json(args.development_prior),
        gate.read_json(args.holdout) if args.holdout else None,
    )
    gate.write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

