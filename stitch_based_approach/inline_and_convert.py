#!/usr/bin/env python3
"""
Pre-process Python programs to inline intermediate variables, then convert to Stitch.

This solves the free variable problem by symbolically inlining all local assignments
before converting to lambda calculus.
"""
import ast
import json
import sys
from typing import Dict, Optional


class VariableInliner(ast.NodeTransformer):
    """Inline all local variable assignments into the return statement."""

    def __init__(self):
        self.assignments = {}  # Maps variable names to their AST expressions

    def visit_FunctionDef(self, node):
        """Process function: collect assignments and inline into return."""
        self.assignments = {}

        # Collect all assignments
        new_body = []
        return_stmt = None

        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                # Store the assignment
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        self.assignments[target.id] = stmt.value
                    elif isinstance(target, ast.Tuple):
                        # Handle tuple unpacking like: rows, _ = np.where(...)
                        if isinstance(stmt.value, ast.Call):
                            # For simplicity, skip tuple unpacking - too complex
                            pass
            elif isinstance(stmt, ast.Return):
                return_stmt = stmt
            elif not isinstance(stmt, (ast.Expr, ast.Pass)):
                # Keep non-assignment statements (but this will make conversion fail)
                new_body.append(stmt)

        # Now inline variables into the return statement
        if return_stmt and return_stmt.value:
            inlined_expr = self.visit(return_stmt.value)
            return_stmt.value = inlined_expr
            new_body.append(return_stmt)

        node.body = new_body
        return node

    def visit_Name(self, node):
        """Replace variable references with their definitions."""
        if isinstance(node.ctx, ast.Load) and node.id in self.assignments:
            # Return a copy of the assigned expression
            return ast.copy_location(
                self.visit(self.assignments[node.id]),
                node
            )
        return node


def inline_variables(code: str) -> Optional[str]:
    """Inline all intermediate variables in Python code."""
    try:
        tree = ast.parse(code)
        inliner = VariableInliner()
        new_tree = inliner.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
    except Exception as e:
        return None


# Import the converter from the fixed version
import sys
sys.path.insert(0, '/home/ubuntu/cs2520/stitch_based_approach')
from battleship_to_stitch_fixed import convert_program


def main():
    """Process all programs: inline variables then convert to Stitch."""
    input_file = '../battleship_programs.jsonl'
    output_file = 'battleship_stitch_inlined.json'

    programs = []
    successful = 0
    failed_inline = 0
    failed_convert = 0

    print("Inlining variables and converting to Stitch...")
    print()

    with open(input_file, 'r') as f:
        for i, line in enumerate(f, 1):
            entry = json.loads(line)
            code = entry['solution']

            # Step 1: Inline variables
            inlined_code = inline_variables(code)

            if not inlined_code:
                failed_inline += 1
                continue

            # Step 2: Convert to Stitch
            sexp, free_vars = convert_program(inlined_code)

            if sexp and sexp != 'None':
                programs.append(sexp)
                successful += 1

                if free_vars and len(free_vars) > 0:
                    print(f"Program {i} still has free vars after inlining: {free_vars}")
            else:
                failed_convert += 1

            if i % 100 == 0:
                print(f"Processed {i} programs...")

    total = successful + failed_inline + failed_convert
    print()
    print(f"✓ Successfully inlined & converted: {successful}/{total}")
    print(f"✗ Failed to inline: {failed_inline}/{total}")
    print(f"✗ Failed to convert: {failed_convert}/{total}")
    print()

    # Save results
    with open(output_file, 'w') as f:
        json.dump(programs, f, indent=2)
    print(f"✓ Saved {len(programs)} programs to {output_file}")

    # Show examples
    if programs:
        print()
        print("Example programs:")
        for i, prog in enumerate(programs[:5], 1):
            print(f"{i}. {prog}")


if __name__ == '__main__':
    main()
