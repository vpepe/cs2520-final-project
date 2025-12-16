#!/usr/bin/env python3
"""
Convert Python Battleship programs to SIMPLIFIED lambda calculus for Stitch.

This version creates a much simpler DSL that Stitch can actually handle:
- Single-letter or simple word primitives (no hyphens, no special chars)
- Flattened let-bindings where possible
- Simplified type system
"""
import ast
import json
import sys
from typing import Any, Dict, List, Tuple


# Map Python operations to simple primitives
PRIMITIVE_MAP = {
    # Numpy operations
    'np.any': 'any',
    'np.all': 'all',
    'np.sum': 'sum',
    'np.where': 'where',
    'np.unique': 'unique',
    'np.argwhere': 'argwhere',
    'np.count_nonzero': 'count',

    # Comparison operations
    'eq': 'eq',
    'gt': 'gt',
    'lt': 'lt',
    'gte': 'gte',
    'lte': 'lte',
    'ne': 'ne',

    # Arithmetic
    'add': 'add',
    'sub': 'sub',
    'mul': 'mul',
    'div': 'div',

    # Boolean
    'and': 'and',
    'or': 'or',
    'not': 'not',

    # Array operations
    'subscript': 'get',
    'slice': 'slice',

    # Type conversions
    'bool': 'tobool',
    'int': 'toint',
    'str': 'tostr',

    # String operations
    'ord': 'ord',
    'upper': 'upper',
    'lower': 'lower',

    # Tuple/pair
    'pair': 'pair',
    'fst': 'fst',
    'snd': 'snd',
}


class SimplifiedStitchConverter(ast.NodeVisitor):
    """Convert Python AST to simplified Stitch s-expressions."""

    def __init__(self):
        self.var_stack = []  # Track lambda-bound variables

    def to_sexp(self, term) -> str:
        """Convert term tuple to s-expression string."""
        if isinstance(term, str):
            return term
        elif isinstance(term, (int, float)):
            return str(term)
        elif isinstance(term, tuple):
            if len(term) == 0:
                return '()'
            return '(' + ' '.join(self.to_sexp(t) for t in term) + ')'
        else:
            return str(term)

    def visit_Module(self, node):
        """Visit module."""
        if node.body:
            return self.visit(node.body[0])
        return 'unit'

    def visit_FunctionDef(self, node):
        """Convert function to lambda."""
        # Extract parameters
        params = [arg.arg for arg in node.args.args]

        # Build nested lambdas
        body = None
        if node.body:
            # Find return statement
            for stmt in node.body:
                if isinstance(stmt, ast.Return):
                    body = self.visit(stmt.value)
                    break

        if body is None:
            body = 'unit'

        # Wrap in lambdas (innermost first for de Bruijn indices)
        for param in reversed(params):
            self.var_stack.insert(0, param)
            body = ('lam', body)

        return body

    def visit_Return(self, node):
        """Visit return statement."""
        return self.visit(node.value)

    def visit_Name(self, node):
        """Visit variable reference."""
        name = node.id

        # Check if it's a lambda-bound variable
        if name in self.var_stack:
            idx = self.var_stack.index(name)
            return f'#{idx}'

        # Map to simple primitive
        simple_name = PRIMITIVE_MAP.get(name, name)
        # Remove hyphens and special chars
        simple_name = simple_name.replace('-', '').replace('_', '')
        return simple_name

    def visit_Constant(self, node):
        """Visit constant."""
        val = node.value
        if isinstance(val, bool):
            return 'true' if val else 'false'
        elif isinstance(val, str):
            # Single char strings are OK
            if len(val) == 1:
                return f"'{val}'"
            # Map known strings
            return f'str{hash(val) % 100}'
        elif isinstance(val, (int, float)):
            # Make sure it's a valid number
            return str(int(val)) if isinstance(val, int) else str(float(val))
        return 'unit'

    def visit_BinOp(self, node):
        """Visit binary operation."""
        left = self.visit(node.left)
        right = self.visit(node.right)

        op_map = {
            ast.Add: 'add',
            ast.Sub: 'sub',
            ast.Mult: 'mul',
            ast.Div: 'div',
            ast.Mod: 'mod',
            ast.BitAnd: 'and',
            ast.BitOr: 'or',
            ast.BitXor: 'xor',
        }

        op = op_map.get(type(node.op), 'binop')
        return ('app', ('app', op, left), right)

    def visit_Compare(self, node):
        """Visit comparison."""
        left = self.visit(node.left)

        # Handle single comparison
        if len(node.ops) == 1 and len(node.comparators) == 1:
            op = node.ops[0]
            right = self.visit(node.comparators[0])

            op_map = {
                ast.Eq: 'eq',
                ast.NotEq: 'ne',
                ast.Lt: 'lt',
                ast.LtE: 'lte',
                ast.Gt: 'gt',
                ast.GtE: 'gte',
            }

            op_name = op_map.get(type(op), 'cmp')
            return ('app', ('app', op_name, left), right)

        # Multiple comparisons - just take first
        return self.visit_Compare(
            ast.Compare(left=node.left,
                       ops=[node.ops[0]],
                       comparators=[node.comparators[0]])
        )

    def visit_Call(self, node):
        """Visit function call."""
        # Get function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Handle np.any, etc.
            if isinstance(node.func.value, ast.Name):
                module = node.func.value.id
                attr = node.func.attr
                func_name = f'{module}.{attr}'
            else:
                func_name = node.func.attr
        else:
            func_name = 'call'

        # Map to simple primitive
        func_name = PRIMITIVE_MAP.get(func_name, func_name)
        func_name = func_name.replace('-', '').replace('_', '')

        # Build application chain
        result = func_name
        for arg in node.args:
            arg_term = self.visit(arg)
            result = ('app', result, arg_term)

        return result

    def visit_Subscript(self, node):
        """Visit subscript."""
        value = self.visit(node.value)
        idx = self.visit(node.slice)
        return ('app', ('app', 'get', value), idx)

    def visit_Index(self, node):
        """Visit index (deprecated in Python 3.9+)."""
        return self.visit(node.value)

    def visit_Tuple(self, node):
        """Visit tuple."""
        if len(node.elts) == 2:
            fst = self.visit(node.elts[0])
            snd = self.visit(node.elts[1])
            return ('app', ('app', 'pair', fst), snd)
        elif len(node.elts) == 0:
            return 'unit'
        else:
            # Build nested pairs
            result = self.visit(node.elts[-1])
            for elt in reversed(node.elts[:-1]):
                elt_term = self.visit(elt)
                result = ('app', ('app', 'pair', elt_term), result)
            return result

    def visit_Slice(self, node):
        """Visit slice."""
        # Simplified: just use slice primitive
        lower = self.visit(node.lower) if node.lower else 'none'
        upper = self.visit(node.upper) if node.upper else 'none'
        return ('app', ('app', 'slice', lower), upper)

    def visit_Attribute(self, node):
        """Visit attribute access."""
        return self.visit(node.value)

    def visit_BoolOp(self, node):
        """Visit boolean operation."""
        op_name = 'and' if isinstance(node.op, ast.And) else 'or'

        # Build chain
        result = self.visit(node.values[0])
        for val in node.values[1:]:
            val_term = self.visit(val)
            result = ('app', ('app', op_name, result), val_term)
        return result

    def visit_UnaryOp(self, node):
        """Visit unary operation."""
        operand = self.visit(node.operand)

        if isinstance(node.op, ast.Not):
            return ('app', 'not', operand)
        elif isinstance(node.op, ast.USub):
            return ('app', 'neg', operand)
        else:
            return operand

    def generic_visit(self, node):
        """Fallback for unknown nodes."""
        return 'unknown'


def convert_program(code: str, description: str) -> str:
    """Convert Python code to simplified Stitch s-expression."""
    try:
        tree = ast.parse(code)
        converter = SimplifiedStitchConverter()
        term = converter.visit(tree)
        return converter.to_sexp(term)
    except Exception as e:
        print(f"Error converting '{description}': {e}", file=sys.stderr)
        return None


def main():
    """Convert all Battleship programs."""
    input_file = '../battleship_programs.jsonl'
    output_file = 'battleship_simple_stitch.json'

    programs = []
    successful = 0
    failed = 0

    print("Converting Battleship programs to simplified lambda calculus...")
    print()

    with open(input_file, 'r') as f:
        for i, line in enumerate(f, 1):
            entry = json.loads(line)
            desc = entry['description']
            code = entry['solution']

            sexp = convert_program(code, desc)
            if sexp:
                programs.append(sexp)
                successful += 1
            else:
                failed += 1

            if i % 100 == 0:
                print(f"Processed {i} programs...")

    print()
    print(f"✓ Successfully converted: {successful}/{successful+failed}")
    print(f"✗ Failed: {failed}/{successful+failed}")
    print()

    # Save as JSON
    with open(output_file, 'w') as f:
        json.dump(programs, f, indent=2)

    print(f"✓ Saved to {output_file}")

    # Also create sample for testing
    sample_file = 'sample_simple_50.json'
    with open(sample_file, 'w') as f:
        json.dump(programs[:50], f, indent=2)

    print(f"✓ Sample saved to {sample_file}")

    # Show example
    if programs:
        print()
        print("Example program:")
        print(programs[0])


if __name__ == '__main__':
    main()
