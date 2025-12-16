"""
Convert Python Battleship programs to Stitch's lambda calculus format.

Stitch expects programs as s-expressions in lambda calculus:
  (app f x)         - function application
  (lam body)        - lambda abstraction
  var names         - variables and primitives

We'll create a domain-specific language for Battleship operations
and convert Python programs to this DSL.
"""
import ast
import json
from typing import List, Dict, Set


class BattleshipDSL:
    """Domain-specific language for Battleship operations."""

    # Primitives
    PRIMITIVES = {
        # Board access
        'true-board',
        'partial-board',

        # Numpy operations
        'np-any', 'np-all', 'np-where', 'np-argwhere', 'np-unique',
        'np-sum', 'np-nonzero',

        # Comparisons
        'gt', 'lt', 'eq', 'ne', 'gte', 'lte',

        # Boolean ops
        'and', 'or', 'not',

        # Array ops
        'subscript', 'slice',

        # Arithmetic
        'add', 'sub', 'mul', 'div',

        # Constants
        '0', '1', '2', '3', '4', '-1',

        # Type conversions
        'bool', 'int',

        # Special
        'ord', 'ord-A',
    }

    @staticmethod
    def to_sexp(expr) -> str:
        """Convert to s-expression format."""
        if isinstance(expr, str):
            return expr
        elif isinstance(expr, tuple):
            if len(expr) == 0:
                return "()"
            op = expr[0]
            args = ' '.join(BattleshipDSL.to_sexp(arg) for arg in expr[1:])
            return f"({op} {args})" if args else f"{op}"
        else:
            return str(expr)


class PythonToStitch(ast.NodeVisitor):
    """Convert Python AST to Stitch lambda calculus."""

    def __init__(self):
        self.var_counter = 0
        self.primitives_used = set()

    def fresh_var(self) -> str:
        """Generate a fresh variable name."""
        var = f"$v{self.var_counter}"
        self.var_counter += 1
        return var

    def visit_FunctionDef(self, node):
        """Extract function body."""
        if node.name == 'answer':
            # Build a lambda for the function
            # answer(true_board, partial_board) -> ...
            # becomes: (lam (lam body))
            if len(node.body) == 1 and isinstance(node.body[0], ast.Return):
                body = self.visit(node.body[0].value)
                return ('lam', ('lam', body))
            else:
                # Multiple statements - convert to let bindings
                bindings = []
                for stmt in node.body[:-1]:
                    if isinstance(stmt, ast.Assign):
                        bindings.append(self.visit(stmt))

                ret_val = self.visit(node.body[-1].value) if isinstance(node.body[-1], ast.Return) else None

                # Build nested lets
                result = ret_val
                for var, val in reversed(bindings):
                    result = ('let', var, val, result)

                return ('lam', ('lam', result))

    def visit_Assign(self, node):
        """Assignment -> let binding."""
        target = node.targets[0]
        value = self.visit(node.value)

        if isinstance(target, ast.Name):
            return (target.id, value)
        return (self.fresh_var(), value)

    def visit_Return(self, node):
        """Return statement."""
        return self.visit(node.value) if node.value else '()'

    def visit_Name(self, node):
        """Variable reference."""
        # Map Python names to our DSL
        name_map = {
            'true_board': 'true-board',
            'partial_board': 'partial-board',
            'np': 'np',
            'True': '1',
            'False': '0',
            'None': '()',
        }
        return name_map.get(node.id, node.id)

    def visit_Constant(self, node):
        """Constants."""
        if node.value is True:
            return '1'
        elif node.value is False:
            return '0'
        elif node.value is None:
            return '()'
        elif isinstance(node.value, int):
            return str(node.value)
        else:
            return f'"{node.value}"'

    def visit_BinOp(self, node):
        """Binary operations."""
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
        }

        op = op_map.get(type(node.op), 'unknown')
        self.primitives_used.add(op)
        return ('app', ('app', op, left), right)

    def visit_Compare(self, node):
        """Comparisons."""
        left = self.visit(node.left)
        op_type = type(node.ops[0])
        right = self.visit(node.comparators[0])

        op_map = {
            ast.Gt: 'gt',
            ast.Lt: 'lt',
            ast.Eq: 'eq',
            ast.NotEq: 'ne',
            ast.GtE: 'gte',
            ast.LtE: 'lte',
        }

        op = op_map.get(op_type, 'unknown')
        self.primitives_used.add(op)
        return ('app', ('app', op, left), right)

    def visit_BoolOp(self, node):
        """Boolean operations."""
        op_map = {
            ast.And: 'and',
            ast.Or: 'or',
        }

        op = op_map.get(type(node.op), 'unknown')
        self.primitives_used.add(op)

        # Fold multiple operands
        result = self.visit(node.values[0])
        for val in node.values[1:]:
            result = ('app', ('app', op, result), self.visit(val))

        return result

    def visit_Call(self, node):
        """Function calls."""
        func = self.visit(node.func)

        # Special handling for numpy functions
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'np':
                func_name = f'np-{node.func.attr}'
                self.primitives_used.add(func_name)

                # Apply arguments
                result = func_name
                for arg in node.args:
                    result = ('app', result, self.visit(arg))
                return result

        # Regular function application
        result = func
        for arg in node.args:
            result = ('app', result, self.visit(arg))

        return result

    def visit_Attribute(self, node):
        """Attribute access."""
        value = self.visit(node.value)
        return f"{value}.{node.attr}"

    def visit_Subscript(self, node):
        """Array subscripting."""
        value = self.visit(node.value)
        index = self.visit(node.slice)

        self.primitives_used.add('subscript')
        return ('app', ('app', 'subscript', value), index)

    def visit_Tuple(self, node):
        """Tuple."""
        if len(node.elts) == 2:
            # Binary tuple
            return ('pair', self.visit(node.elts[0]), self.visit(node.elts[1]))
        else:
            # Nested pairs
            result = self.visit(node.elts[-1])
            for elt in reversed(node.elts[:-1]):
                result = ('pair', self.visit(elt), result)
            return result

    def visit_Slice(self, node):
        """Slice notation."""
        lower = self.visit(node.lower) if node.lower else '0'
        upper = self.visit(node.upper) if node.upper else 'inf'
        return ('slice', lower, upper)

    def generic_visit(self, node):
        """Fallback."""
        return 'unknown'


def python_to_stitch(code: str) -> str:
    """Convert Python code to Stitch s-expression."""
    try:
        tree = ast.parse(code)
        converter = PythonToStitch()

        # Find the answer function
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == 'answer':
                result = converter.visit(node)
                return BattleshipDSL.to_sexp(result)

        return "(error no-answer-function)"
    except Exception as e:
        return f"(error {str(e)})"


def convert_programs_to_stitch(programs_file: str, output_file: str):
    """Convert all programs to Stitch format."""

    with open(programs_file, 'r') as f:
        programs = [json.loads(line) for line in f]

    stitch_programs = []
    stats = {
        'total': len(programs),
        'converted': 0,
        'errors': 0,
        'primitives_used': set()
    }

    for i, prog in enumerate(programs):
        sexp = python_to_stitch(prog['solution'])

        if not sexp.startswith('(error'):
            stitch_programs.append(sexp)
            stats['converted'] += 1
        else:
            stats['errors'] += 1
            print(f"Error converting program {i}: {sexp}")

    # Save as JSON array (Stitch format)
    with open(output_file, 'w') as f:
        json.dump(stitch_programs, f, indent=2)

    # Also save with descriptions
    with open(output_file.replace('.json', '_annotated.txt'), 'w') as f:
        for prog, sexp in zip(programs[:stats['converted']], stitch_programs):
            f.write(f";; {prog.get('name', 'unknown')}: {prog['description']}\n")
            f.write(f"{sexp}\n\n")

    print(f"\n{'='*70}")
    print("CONVERSION STATISTICS")
    print(f"{'='*70}")
    print(f"Total programs:      {stats['total']}")
    print(f"Successfully converted: {stats['converted']}")
    print(f"Errors:              {stats['errors']}")
    print(f"Success rate:        {100 * stats['converted'] / stats['total']:.1f}%")
    print(f"\nOutput saved to: {output_file}")

    return stitch_programs


if __name__ == '__main__':
    # Test with example
    example_code = """
import numpy as np

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    row = 6
    unrevealed = (partial_board[row, :] == -1)
    ship_tiles = (true_board[row, :] > 0)
    return bool(np.any(unrevealed & ship_tiles))
"""

    print("Example conversion:")
    print("="*70)
    print("Python:")
    print(example_code)
    print("\nStitch s-expression:")
    sexp = python_to_stitch(example_code)
    print(sexp)
    print("="*70)

    # Convert all programs
    programs = convert_programs_to_stitch(
        '../battleship_programs.jsonl',
        'battleship_for_stitch.json'
    )
