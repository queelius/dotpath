import argparse
import sys
import json

try:
    import yaml
except ImportError:
    yaml = None

from .core import create_default_engine

def main():
    """The command-line interface for dotpath."""
    parser = argparse.ArgumentParser(
        description="Query or transform JSON/YAML data using dotpath expressions."
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--to-json',
        action='store_true',
        help="Parse the path string and print its serialized JSON AST instead of evaluating it."
    )
    mode_group.add_argument(
        '--from-json',
        action='store_true',
        help="Evaluate a path from a JSON AST file, provided as the <path> argument."
    )

    parser.add_argument(
        'path',
        help="The dotpath-x string or, with --from-json, the path to a file containing a JSON AST."
    )
    parser.add_argument(
        'data_file',
        nargs='?',
        default='-',
        help="Path to the data file (JSON or YAML). Defaults to stdin."
    )
    parser.add_argument(
        '-f', '--first',
        action='store_true',
        help="Return only the first matching result instead of all results."
    )
    parser.add_argument(
        '--in', '--input-format',
        dest='input_format',
        choices=['json', 'yaml'],
        help="Format of the input data. Inferred from file extension if not provided."
    )

    args = parser.parse_args()
    engine = create_default_engine()

    # Mode 1: Parse a path string to its JSON AST representation
    if args.to_json:
        if args.from_json:
            parser.error("--to-json cannot be used with --from-json.")
        try:
            ast = engine.parse(args.path)
            print(engine.ast_to_json(ast))
            sys.exit(0)
        except ValueError as e:
            print(f"Error parsing path: {e}", file=sys.stderr)
            sys.exit(1)

    # --- Evaluation Modes ---
    
    # Load data
    try:
        if args.data_file == '-':
            data_stream = sys.stdin
        else:
            data_stream = open(args.data_file, 'r')

        input_format = args.input_format
        if not input_format:
            if args.data_file != '-' and args.data_file.lower().endswith(('.yml', '.yaml')):
                input_format = 'yaml'
            else:
                input_format = 'json'

        if input_format == 'yaml':
            if not yaml:
                print("YAML format requires the 'PyYAML' package. `pip install PyYAML`", file=sys.stderr)
                sys.exit(1)
            data = yaml.safe_load(data_stream)
        else:
            data = json.load(data_stream)
    except Exception as e:
        print(f"Error loading data: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'data_stream' in locals() and data_stream is not sys.stdin:
            data_stream.close()

    # Get the AST, either from a string or a JSON file
    try:
        if args.from_json:
            with open(args.path, 'r') as f:
                json_ast_str = f.read()
            ast = engine.json_to_ast(json_ast_str)
        else:
            ast = engine.parse(args.path)
    except Exception as e:
        print(f"Error processing path: {e}", file=sys.stderr)
        sys.exit(1)

    # Evaluate the AST against the data
    results = engine.evaluate(ast, data)

    # Output the results
    try:
        if args.first:
            result = next(results, None)
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(list(results), indent=2))
    except (StopIteration, TypeError):
        pass # No results found is