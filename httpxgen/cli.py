import argparse
from pathlib import Path

from httpxgen.generator import GenerationError
from httpxgen.io import (
    filter_operations_by_tags,
    load_openapi,
    write_client,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a typed async Python client from OpenAPI JSON."
    )
    parser.add_argument("openapi", type=Path, help="OpenAPI JSON file")
    parser.add_argument("output", type=Path, help="exact target package directory")
    parser.add_argument(
        "--package-name",
        help="generated import package name; defaults to the output directory name",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail when generated output is stale",
    )
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        metavar="TAG",
        help="include only operations with this OpenAPI tag; may be repeated",
    )
    parser.add_argument(
        "--schema-tag",
        dest="schema_tags",
        action="append",
        default=[],
        metavar="TAG",
        help="retain schemas referenced by this tag without generating its operations",
    )
    args = parser.parse_args()

    try:
        spec = load_openapi(args.openapi)
        spec = filter_operations_by_tags(
            spec,
            args.tags,
            schema_tags=args.schema_tags,
        )
        changed = write_client(
            spec=spec,
            package_dir=args.output,
            package_name=args.package_name,
            check=args.check,
        )
    except (GenerationError, OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")

    if args.check:
        print("Generated HTTP client is current.")
    else:
        print(f"Generated {len(changed)} file(s) in package {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
