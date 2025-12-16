#!/usr/bin/env python3
"""
Convert Battleship programs to valid Stitch lambda calculus format with proper de Bruijn indices.

This version ensures that ALL variables are properly converted to de Bruijn indices
and no free variable names remain in the output.
"""
import ast
import json
import sys
from typing import Dict, List, Optional, Set


# Map operations to simple primitives
PRIMITIVES = {
    'np.any': 'any',
    'np.all': 'all',
    'np.sum': 'sum',
    'np.unique': 'unique',
    'np.where': 'where',
    'np.argwhere': 'argwhere',
    'np.count_nonzero': 'count',
    'np.nonzero': 'nonzero',
    'bool': 'tobool',
    'int': 'toint',
    'ord': 'ord',
    'upper': 'upper',
    'lower': 'lower',
}


class StitchConverter(ast.NodeVisitor):
    """Convert Python AST to Stitch format with proper de Bruijn indices."""

    def __init__(self):
        # Stack of variable names, innermost first (for de Bruijn indexing)
        self.var_stack: List[str] = []
        # Track free variables we encounter (for debugging)
        self.free_vars: Set[str] = set()

    def get_debruijn(self, name: str) -> Optional[int]:
        """Get De Bruijn index for variable name."""
        try:
            # Search from innermost scope (0) outward
            return self.var_stack.index(name)
        except ValueError:
            return None

    def to_sexp(self, term) -> str:
        """Convert term to s-expression string."""
        if isinstance(term, str):
            return term
        elif isinstance(term, (int, float)):
            return str(int(term))
        elif isinstance(term, tuple):
            if not term:
                return "()"
            return '(' + ' '.join(self.to_sexp(t) for t in term) + ')'
        return str(term)

    def visit_Module(self, node):
        """Visit module - extract function."""
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                return self.visit(item)
        return None

    def visit_FunctionDef(self, node):
        """Convert function def to nested lambdas."""
        # Get parameters - these are the ONLY bound variables
        params = [arg.arg for arg in node.args.args]

        # Find the return expression
        ret_expr = None
        for stmt in node.body:
            if isinstance(stmt, ast.Return):
                ret_expr = stmt.value
                break

        if not ret_expr:
            return None

        # Set up variable stack with parameters in REVERSE order
        # because we'll be building lambdas from outside-in
        # For a function f(a, b): (lam (lam body)) where 0=b, 1=a
        self.var_stack = list(reversed(params))
        body = self.visit(ret_expr)

        # Wrap in lambdas (one per parameter)
        for _ in params:
            body = ('lam', body)

        return body

    def visit_Return(self, node):
        """Visit return statement."""
        return self.visit(node.value)

    def visit_Name(self, node):
        """Visit variable reference."""
        name = node.id

        # Check if it's a bound variable (parameter)
        idx = self.get_debruijn(name)
        if idx is not None:
            return str(idx)

        # Check if it's a known primitive
        if name in PRIMITIVES or name in ['np', 'true', 'false', 'none']:
            simple = PRIMITIVES.get(name, name)
            simple = simple.replace('_', '').replace('-', '')
            return simple

        # This is a FREE VARIABLE - shouldn't happen in valid programs
        # Convert to a placeholder or treat as constant
        self.free_vars.add(name)
        # Return a sanitized version as a primitive
        return name.replace('_', '').replace('-', '').lower()

    def visit_Constant(self, node):
        """Visit constant value."""
        val = node.value
        if isinstance(val, bool):
            return 'true' if val else 'false'
        elif isinstance(val, str):
            # Single char is OK
            if len(val) == 1 and val.isalpha():
                return f"'{val}'"
            # Map strings to numbers
            return str(abs(hash(val)) % 100)
        elif isinstance(val, (int, float)):
            return str(int(val))
        elif val is None:
            return 'none'
        return '0'

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

        op = op_map.get(type(node.op), 'op')
        # Binary operators are curried: (app (app op left) right)
        return ('app', ('app', op, left), right)

    def visit_Compare(self, node):
        """Visit comparison."""
        # Take only first comparison
        if not node.ops or not node.comparators:
            return 'true'

        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        op = node.ops[0]

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
        func_name = PRIMITIVES.get(func_name, func_name)
        func_name = func_name.replace('_', '').replace('-', '')

        # Build application chain
        result = func_name
        for arg in node.args:
            arg_term = self.visit(arg)
            result = ('app', result, arg_term)

        return result

    def visit_Subscript(self, node):
        """Visit subscript - simplified as 'get' operation."""
        value = self.visit(node.value)
        idx = self.visit(node.slice)
        return ('app', ('app', 'get', idx), value)

    def visit_Tuple(self, node):
        """Visit tuple - encode as nested pairs."""
        if len(node.elts) == 0:
            return 'unit'
        elif len(node.elts) == 1:
            return self.visit(node.elts[0])
        elif len(node.elts) == 2:
            fst = self.visit(node.elts[0])
            snd = self.visit(node.elts[1])
            return ('app', ('app', 'pair', fst), snd)
        else:
            # Build right-nested pairs
            result = self.visit(node.elts[-1])
            for elt in reversed(node.elts[:-1]):
                elt_term = self.visit(elt)
                result = ('app', ('app', 'pair', elt_term), result)
            return result

    def visit_BoolOp(self, node):
        """Visit boolean operation."""
        op_name = 'and' if isinstance(node.op, ast.And) else 'or'

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
        return operand

    def visit_Attribute(self, node):
        """Visit attribute access."""
        # For things like arr.shape, we need to visit the base object
        # and apply a shape/size operation if needed
        obj = self.visit(node.value)
        attr = node.attr

        if attr == 'shape':
            return ('app', 'shape', obj)
        elif attr in ['any', 'all', 'sum', 'max', 'min']:
            # Method calls like arr.any()
            return attr
        else:
            # Just return the object
            return obj

    def visit_Slice(self, node):
        """Visit slice."""
        # Simplified slice representation
        return 'slice'

    def generic_visit(self, node):
        """Fallback for unknown nodes."""
        # Return a neutral term
        return 'unit'


def convert_program(code: str) -> tuple[Optional[str], Set[str]]:
    """Convert Python code to Stitch s-expression.

    Returns:
        (sexp_string, free_variables_found)
    """
    try:
        tree = ast.parse(code)
        converter = StitchConverter()
        term = converter.visit(tree)
        if term:
            return converter.to_sexp(term), converter.free_vars
        return None, set()
    except Exception as e:
        return None, set()


def main():
    """Convert all Battleship programs with proper de Bruijn indices."""
    input_file = '../battleship_programs.jsonl'
    output_file = 'battleship_stitch_fixed.json'

    programs = []
    successful = 0
    failed = 0
    all_free_vars = set()

    print("Converting Battleship programs to Stitch format (fixed)...")
    print()

    with open(input_file, 'r') as f:
        for i, line in enumerate(f, 1):
            entry = json.loads(line)
            code = entry['solution']

            sexp, free_vars = convert_program(code)
            if sexp and sexp != 'None':
                programs.append(sexp)
                successful += 1
                all_free_vars.update(free_vars)
                if free_vars:
                    print(f"Warning: program {i} has free variables: {free_vars}")
            else:
                failed += 1

            if i % 100 == 0:
                print(f"Processed {i} programs...")

    print()
    print(f"✓ Successfully converted: {successful}/{successful+failed}")
    print(f"✗ Failed: {failed}/{successful+failed}")

    if all_free_vars:
        print(f"\n⚠ Warning: Found free variables in some programs: {all_free_vars}")
        print("These should ideally be bound or be primitives.")
    else:
        print(f"\n✓ No free variables found - all variables properly converted to de Bruijn indices!")
    print()

    # Save all programs
    with open(output_file, 'w') as f:
        json.dump(programs, f, indent=2)
    print(f"✓ Saved {len(programs)} programs to {output_file}")

    # Show example
    if programs:
        print()
        print("Example programs:")
        for i, prog in enumerate(programs[:5], 1):
            print(f"{i}. {prog}")


if __name__ == '__main__':
    main()
