#!/usr/bin/env python3
"""
Track what free variables represent in the original Python code.

This creates a mapping from (program_id, canonical_var) → original_computation
so we can reconstruct the full Python code after Stitch compression.
"""
import ast
import json
import re


class VariableTracker(ast.NodeVisitor):
    """Track all variable assignments in Python code."""

    def __init__(self):
        self.assignments = {}  # name -> ast expression
        self.order = []  # Order of first appearance

    def visit_Assign(self, node):
        """Record variable assignments."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assignments[target.id] = ast.unparse(node.value)
                if target.id not in self.order:
                    self.order.append(target.id)
            elif isinstance(target, ast.Tuple):
                # Tuple unpacking like: rows, _ = np.where(...)
                if isinstance(node.value, ast.Call):
                    # Store the call
                    call_str = ast.unparse(node.value)
                    for i, elt in enumerate(target.elts):
                        if isinstance(elt, ast.Name):
                            self.assignments[elt.id] = f"{call_str}[{i}]"
                            if elt.id not in self.order:
                                self.order.append(elt.id)
        self.generic_visit(node)

    def visit_For(self, node):
        """Track for loop variables."""
        if isinstance(node.target, ast.Name):
            self.assignments[node.target.id] = "loop_variable"
            if node.target.id not in self.order:
                self.order.append(node.target.id)
        self.generic_visit(node)


def extract_variables_from_python(code: str) -> dict:
    """Extract all variable assignments from Python code."""
    try:
        tree = ast.parse(code)
        tracker = VariableTracker()
        tracker.visit(tree)
        return {
            'assignments': tracker.assignments,
            'order': tracker.order
        }
    except:
        return {'assignments': {}, 'order': []}


def build_free_var_mapping():
    """Build mapping from canonical vars to original computations."""

    # Load original Python programs
    programs = []
    with open('../battleship_programs.jsonl', 'r') as f:
        for i, line in enumerate(f):
            entry = json.loads(line)
            programs.append({
                'index': i,
                'code': entry['solution'],
                'name': entry['name']
            })

    # Load the original (non-canonical) Stitch version to see original var names
    with open('battleship_stitch_fixed.json') as f:
        stitch_original = json.load(f)

    # Load canonical version
    with open('battleship_stitch_canonical.json') as f:
        stitch_canonical = json.load(f)

    # Build mapping
    mapping = {}

    for i, prog in enumerate(programs):
        if i >= len(stitch_original):
            break

        # Extract variables from Python
        var_info = extract_variables_from_python(prog['code'])

        # Extract free variables from both versions
        orig_free_vars = set(re.findall(r'\b[a-z_][a-z0-9_]+\b', stitch_original[i]))
        canon_free_vars = set(re.findall(r'\bv\d+\b', stitch_canonical[i]))

        # Remove primitives
        primitives = {
            'lam', 'app', 'any', 'all', 'sum', 'unique', 'where', 'argwhere',
            'get', 'pair', 'slice', 'tobool', 'gt', 'lt', 'eq', 'ne', 'and', 'or'
        }
        orig_free_vars = orig_free_vars - primitives

        if canon_free_vars:
            # Map canonical vars back to original vars
            var_mapping = {}

            # The order should match
            orig_vars_ordered = [v for v in var_info['order'] if v in orig_free_vars]
            canon_vars_ordered = sorted(canon_free_vars)

            for j, (orig_var, canon_var) in enumerate(zip(orig_vars_ordered, canon_vars_ordered)):
                computation = var_info['assignments'].get(orig_var, f"<unknown: {orig_var}>")
                var_mapping[canon_var] = {
                    'original_name': orig_var,
                    'computation': computation
                }

            if var_mapping:
                mapping[i] = {
                    'program_name': prog['name'],
                    'canonical_program': stitch_canonical[i],
                    'variables': var_mapping
                }

    return mapping


def main():
    """Build and save the free variable mapping."""

    print("Building free variable mapping...")
    print()

    mapping = build_free_var_mapping()

    # Save to JSON
    output_file = 'free_variable_mapping.json'
    with open(output_file, 'w') as f:
        json.dump(mapping, f, indent=2)

    print(f"✓ Saved mapping for {len(mapping)} programs to {output_file}")
    print()

    # Show some examples
    print("Example mappings:")
    print()

    for prog_id in [4, 12, 13]:
        if str(prog_id) in mapping:
            info = mapping[str(prog_id)]
            print(f"Program {prog_id}: {info['program_name']}")
            print(f"  Canonical: {info['canonical_program'][:80]}...")
            print(f"  Variables:")
            for var, details in info['variables'].items():
                print(f"    {var} = {details['original_name']}")
                print(f"         ← {details['computation']}")
            print()

    print("=" * 80)
    print("Now you can reconstruct Python!")
    print("=" * 80)
    print()
    print("Example: Program 12 compressed to fn_5")
    print()
    print("1. Look up mapping[12]['variables']['v0']")
    print("   → original_name: 'concealed_ship_tiles'")
    print("   → computation: '(true_sub > 0) & (partial_sub == -1)'")
    print()
    print("2. Expand fn_5 = bool(np.any(v0))")
    print()
    print("3. Substitute v0:")
    print("   def answer(true_board, partial_board):")
    print("       true_sub = ...")
    print("       partial_sub = ...")
    print("       concealed_ship_tiles = (true_sub > 0) & (partial_sub == -1)")
    print("       return bool(np.any(concealed_ship_tiles))")


if __name__ == '__main__':
    main()