#!/usr/bin/env python3
"""
Canonicalize free variables by renaming them alphabetically.

Instead of having random names like 'rows', 'cols', 'mask', etc.,
rename them to v0, v1, v2, ... in order of first appearance.

This should help stitch find more patterns since semantically equivalent
programs will have the same variable names.
"""
import json
import re
from typing import Set, Dict


# Known primitives that should not be renamed
PRIMITIVES = {
    'lam', 'app', 'any', 'all', 'sum', 'unique', 'where', 'argwhere', 'count',
    'nonzero', 'tobool', 'toint', 'ord', 'upper', 'lower', 'add', 'sub', 'mul',
    'div', 'mod', 'and', 'or', 'xor', 'eq', 'ne', 'lt', 'lte', 'gt', 'gte',
    'not', 'neg', 'get', 'pair', 'slice', 'unit', 'true', 'false', 'none',
    'len', 'set', 'shape', 'max', 'min', 'np', 'arange', 'abs', 'argmax',
    'argmin', 'broadcastto', 'concatenate', 'flatten', 'reshape', 'transpose'
}


def extract_free_vars(sexp: str) -> Set[str]:
    """Extract all free variable names from an s-expression."""
    # Find all identifiers
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', sexp)
    free_vars = set()

    for token in tokens:
        # Skip primitives, de Bruijn indices, and function names
        if token not in PRIMITIVES and not token.startswith('fn_'):
            # Also skip single letters A-H which are row labels
            if not (len(token) == 1 and token in 'ABCDEFGH'):
                free_vars.add(token)

    return free_vars


def canonicalize_program(sexp: str) -> str:
    """Rename free variables to v0, v1, v2, ... in order of appearance."""
    # Extract free variables in order of first appearance
    seen_order = []
    seen_set = set()

    # Scan through and record first appearance order
    tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', sexp)
    for token in tokens:
        if (token not in PRIMITIVES and
            not token.startswith('fn_') and
            not (len(token) == 1 and token in 'ABCDEFGH') and
            token not in seen_set):
            seen_order.append(token)
            seen_set.add(token)

    # Build renaming map
    rename_map = {}
    for i, var in enumerate(seen_order):
        rename_map[var] = f'v{i}'

    # Apply renaming - need to be careful about word boundaries
    result = sexp
    for old_name, new_name in rename_map.items():
        # Use word boundaries to avoid partial matches
        result = re.sub(r'\b' + re.escape(old_name) + r'\b', new_name, result)

    return result


def main():
    """Canonicalize all programs."""
    input_file = 'battleship_stitch_fixed.json'
    output_file = 'battleship_stitch_canonical.json'

    print("Canonicalizing free variables...")
    print()

    with open(input_file, 'r') as f:
        programs = json.load(f)

    canonical_programs = []
    stats = {
        'total': len(programs),
        'had_free_vars': 0,
        'max_free_vars': 0
    }

    for i, prog in enumerate(programs):
        free_vars = extract_free_vars(prog)

        if free_vars:
            stats['had_free_vars'] += 1
            stats['max_free_vars'] = max(stats['max_free_vars'], len(free_vars))

            # Show first few examples
            if stats['had_free_vars'] <= 5:
                canonical = canonicalize_program(prog)
                print(f"Example {stats['had_free_vars']}:")
                print(f"  Original:   {prog[:80]}...")
                print(f"  Free vars:  {sorted(free_vars)}")
                print(f"  Canonical:  {canonical[:80]}...")
                print()

        canonical_programs.append(canonicalize_program(prog))

        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{len(programs)} programs...")

    print()
    print("=" * 70)
    print("STATISTICS")
    print("=" * 70)
    print(f"Total programs:              {stats['total']}")
    print(f"Programs with free vars:     {stats['had_free_vars']} ({100*stats['had_free_vars']/stats['total']:.1f}%)")
    print(f"Max free vars in a program:  {stats['max_free_vars']}")
    print()

    # Save
    with open(output_file, 'w') as f:
        json.dump(canonical_programs, f, indent=2)

    print(f"✓ Saved {len(canonical_programs)} programs to {output_file}")

    # Show more examples
    print()
    print("More examples of canonicalization:")
    for i in [10, 20, 30]:
        if i < len(programs):
            print(f"\nProgram {i}:")
            print(f"  Before: {programs[i][:100]}")
            print(f"  After:  {canonical_programs[i][:100]}")


if __name__ == '__main__':
    main()
