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
        description="Generate a typed async Python client from OpenAPI JSON or YAML."
    )
    parser.add_argument("openapi", type=Path, help="OpenAPI JSON or YAML file")
    parser.add_argument(
        "output",
        type=Path,
        help="target package directory, or the root holding one package per tag "
        "when more than one --tag is given",
    )
    parser.add_argument(
        "--package-name",
        help="generated import package name; defaults to the output directory name",
    )
    parser.add_argument(
        "--client-name",
        help="exact class name for a single generated client",
    )
    parser.add_argument(
        "--http-client",
        choices=("protocol", "httpx", "httpx2"),
        default="protocol",
        help="generated HTTP client type (default: protocol, compatible with both)",
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
        help="include only operations with this OpenAPI tag; repeat it to generate "
        "one package per tag around a shared support package",
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
        if args.client_name and len(args.tags) > 1:
            raise GenerationError(
                "--client-name cannot be used with multi-tag generation"
            )
        if len(args.tags) <= 1:
            spec = filter_operations_by_tags(
                spec,
                args.tags,
                schema_tags=args.schema_tags,
            )
        changed = write_client(
            spec=spec,
            package_dir=args.output,
            package_name=args.package_name,
            client_name=args.client_name,
            tags=args.tags,
            schema_tags=args.schema_tags,
            http_client=args.http_client,
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
