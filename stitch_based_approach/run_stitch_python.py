#!/usr/bin/env python3
"""
Run Stitch compression using Python bindings.
"""
import json
import stitch_core
from typing import List, Dict, Any


def load_programs(filename: str) -> List[str]:
    """Load programs from JSON file."""
    with open(filename, 'r') as f:
        data = json.load(f)

    if isinstance(data, list):
        # List of programs
        return data
    elif 'programs' in data:
        # Dict with 'programs' key
        return data['programs']
    else:
        raise ValueError(f"Unexpected format in {filename}")


def run_stitch(programs: List[str],
               max_arity: int = 3,
               iterations: int = 5,
               threads: int = 4) -> Dict[str, Any]:
    """
    Run Stitch compression on programs.

    Args:
        programs: List of s-expression strings
        max_arity: Maximum function arity
        iterations: Number of compression iterations
        threads: Number of threads to use

    Returns:
        Dictionary with compression results
    """
    print(f"Running Stitch on {len(programs)} programs...")
    print(f"  Max arity: {max_arity}")
    print(f"  Iterations: {iterations}")
    print(f"  Threads: {threads}")
    print()

    # Run compression
    result = stitch_core.compress(
        programs,
        max_arity=max_arity,
        iterations=iterations,
        threads=threads
    )

    return result


def analyze_results(result: Any) -> Dict[str, Any]:
    """Print analysis of Stitch results and return summary dict."""
    print("="*70)
    print("STITCH COMPRESSION RESULTS")
    print("="*70)
    print()

    # Get JSON representation
    if hasattr(result, 'json'):
        result_dict = result.json if isinstance(result.json, dict) else json.loads(result.json)
    else:
        result_dict = {}

    abstractions = result.abstractions if hasattr(result, 'abstractions') else []
    rewritten = result.rewritten if hasattr(result, 'rewritten') else []

    print(f"Abstractions discovered: {len(abstractions)}")
    print(f"Programs rewritten: {len(rewritten)}")
    print()

    if 'dreamcoder' in result_dict:
        dc = result_dict['dreamcoder']
        if 'cost_before_rewrite' in dc and 'cost_after_rewrite' in dc:
            before = dc['cost_before_rewrite']
            after = dc['cost_after_rewrite']
            ratio = before / after if after > 0 else 0

            print(f"Original cost:  {before}")
            print(f"Final cost:     {after}")
            print(f"Compression:    {ratio:.2f}x")
            print()

    print("Discovered abstractions:")
    print("-"*70)

    for i, abstraction in enumerate(abstractions[:10], 1):
        print(f"{i}. {abstraction}")
        print()

    return result_dict


def save_results(result: Dict[str, Any], output_file: str):
    """Save results to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"✓ Results saved to {output_file}")


def generate_python_library(result: Any, result_dict: Dict[str, Any], output_file: str):
    """Generate Python helper library from abstractions."""
    abstractions = result.abstractions if hasattr(result, 'abstractions') else []

    code = "# Stitch-Discovered Helper Library\n"
    code += "# Auto-generated from compression results\n"
    code += "import numpy as np\n\n"

    if not abstractions:
        code += "# No abstractions discovered\n"
    else:
        for i, abstraction in enumerate(abstractions, 1):
            name = f'helper_{i}'
            abs_str = str(abstraction)

            code += f"def {name}(*args):\n"
            code += f'    """\n'
            code += f'    Discovered by Stitch compression.\n'
            code += f'    Pattern: {abs_str[:80]}{"..." if len(abs_str) > 80 else ""}\n'
            code += f'    """\n'
            code += f'    # TODO: Implement based on pattern\n'
            code += f'    # {abs_str}\n'
            code += f'    pass\n\n'

    with open(output_file, 'w') as f:
        f.write(code)

    print(f"✓ Python library saved to {output_file}")


def main():
    """Main entry point."""
    import sys

    # Parse arguments
    input_file = sys.argv[1] if len(sys.argv) > 1 else 'sample_50.json'
    max_arity = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    iterations = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    print(f"Input file: {input_file}")
    print()

    # Load programs
    programs = load_programs(input_file)
    print(f"Loaded {len(programs)} programs")
    print()

    # Run Stitch
    result = run_stitch(programs, max_arity=max_arity, iterations=iterations)

    # Analyze results
    result_dict = analyze_results(result)

    # Save outputs
    output_dir = f"stitch_output_python_iter_{iterations}"
    import os
    os.makedirs(output_dir, exist_ok=True)

    save_results(result_dict, f"{output_dir}/results.json")
    generate_python_library(result, result_dict, f"{output_dir}/stitch_library.py")

    print()
    print("="*70)
    print("✓ Stitch compression complete!")
    print("="*70)


if __name__ == '__main__':
    main()
