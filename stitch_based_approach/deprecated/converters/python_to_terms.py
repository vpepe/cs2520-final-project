"""
Convert Python ASTs to term representation for Stitch.

Stitch expects programs as s-expressions (terms) that can be compressed
via anti-unification. We'll convert Python ASTs to a simplified term language.
"""
import ast
import json
from typing import Any, List, Tuple
from dataclasses import dataclass


@dataclass
class Term:
    """A term in our intermediate representation."""
    op: str
    args: List[Any]

    def to_sexp(self) -> str:
        """Convert to s-expression format."""
        if not self.args:
            return self.op
        args_str = ' '.join(
            arg.to_sexp() if isinstance(arg, Term) else str(arg)
            for arg in self.args
        )
        return f"({self.op} {args_str})"

    def __repr__(self):
        return self.to_sexp()


class PythonToTerms(ast.NodeVisitor):
    """Convert Python AST to term representation."""

    def __init__(self):
        self.terms = []

    def visit_Module(self, node):
        """Top-level module."""
        body_terms = [self.visit(stmt) for stmt in node.body]
        return Term('module', body_terms)

    def visit_FunctionDef(self, node):
        """Function definition."""
        args = [arg.arg for arg in node.args.args]
        body = [self.visit(stmt) for stmt in node.body]
        return Term('defun', [node.name, args, body])

    def visit_Return(self, node):
        """Return statement."""
        value = self.visit(node.value) if node.value else Term('none', [])
        return Term('return', [value])

    def visit_Assign(self, node):
        """Assignment."""
        targets = [self.visit(t) for t in node.targets]
        value = self.visit(node.value)
        return Term('assign', [targets[0], value])

    def visit_AnnAssign(self, node):
        """Annotated assignment."""
        target = self.visit(node.target)
        value = self.visit(node.value) if node.value else Term('none', [])
        return Term('assign', [target, value])

    def visit_Name(self, node):
        """Variable name."""
        return Term('var', [node.id])

    def visit_Constant(self, node):
        """Constant value."""
        return Term('const', [repr(node.value)])

    def visit_BinOp(self, node):
        """Binary operation."""
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_name = node.op.__class__.__name__.lower()
        return Term(op_name, [left, right])

    def visit_Compare(self, node):
        """Comparison."""
        left = self.visit(node.left)
        # Simplify: only handle first comparison
        op = node.ops[0].__class__.__name__.lower()
        right = self.visit(node.comparators[0])
        return Term(op, [left, right])

    def visit_BoolOp(self, node):
        """Boolean operation (and/or)."""
        op_name = node.op.__class__.__name__.lower()
        values = [self.visit(v) for v in node.values]
        # Chain binary operations
        result = values[0]
        for v in values[1:]:
            result = Term(op_name, [result, v])
        return result

    def visit_Call(self, node):
        """Function call."""
        func = self.visit(node.func)
        args = [self.visit(arg) for arg in node.args]
        return Term('call', [func] + args)

    def visit_Attribute(self, node):
        """Attribute access (e.g., np.array)."""
        value = self.visit(node.value)
        return Term('attr', [value, node.attr])

    def visit_Subscript(self, node):
        """Subscripting (array indexing)."""
        value = self.visit(node.value)
        slice_term = self.visit(node.slice)
        return Term('subscript', [value, slice_term])

    def visit_Index(self, node):
        """Index node."""
        return self.visit(node.value)

    def visit_Slice(self, node):
        """Slice node."""
        lower = self.visit(node.lower) if node.lower else Term('none', [])
        upper = self.visit(node.upper) if node.upper else Term('none', [])
        return Term('slice', [lower, upper])

    def visit_Tuple(self, node):
        """Tuple."""
        elts = [self.visit(e) for e in node.elts]
        return Term('tuple', elts)

    def visit_List(self, node):
        """List."""
        elts = [self.visit(e) for e in node.elts]
        return Term('list', elts)

    def visit_IfExp(self, node):
        """Ternary if expression."""
        test = self.visit(node.test)
        body = self.visit(node.body)
        orelse = self.visit(node.orelse)
        return Term('if', [test, body, orelse])

    def generic_visit(self, node):
        """Fallback for unhandled nodes."""
        return Term('unknown', [node.__class__.__name__])


def python_to_term(code: str) -> Term:
    """Convert Python code to term representation."""
    tree = ast.parse(code)
    converter = PythonToTerms()
    return converter.visit(tree)


def extract_function_body_term(code: str) -> Term:
    """Extract just the function body as a term."""
    tree = ast.parse(code)

    # Find the answer function
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == 'answer':
            converter = PythonToTerms()
            # Convert body statements
            body_terms = [converter.visit(stmt) for stmt in node.body]
            return Term('body', body_terms)

    return Term('empty', [])


def programs_to_terms_file(programs_file: str, output_file: str):
    """Convert all programs to term representation and save."""

    with open(programs_file, 'r') as f:
        programs = [json.loads(line) for line in f]

    results = []

    for i, prog in enumerate(programs):
        try:
            term = extract_function_body_term(prog['solution'])
            results.append({
                'id': prog.get('name', f'program_{i}'),
                'description': prog['description'],
                'term': term.to_sexp(),
                'original_code': prog['solution']
            })
        except Exception as e:
            print(f"Error converting program {i}: {e}")
            continue

    # Save as JSON
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Also save as plain s-expressions for Stitch
    sexp_file = output_file.replace('.json', '.sexp')
    with open(sexp_file, 'w') as f:
        for r in results:
            f.write(f";; {r['id']}: {r['description']}\n")
            f.write(f"{r['term']}\n\n")

    print(f"Converted {len(results)} programs to terms")
    print(f"Saved to: {output_file}")
    print(f"S-expressions: {sexp_file}")

    return results


if __name__ == '__main__':
    # Test with a simple example
    test_code = """
import numpy as np

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    row = 6
    unrevealed = (partial_board[row, :] == -1)
    ship_tiles = (true_board[row, :] > 0)
    return bool(np.any(unrevealed & ship_tiles))
"""

    print("Example conversion:")
    print("="*60)
    term = extract_function_body_term(test_code)
    print(term.to_sexp())
    print("="*60)

    # Convert all programs
    results = programs_to_terms_file(
        '../battleship_programs.jsonl',
        'programs_as_terms.json'
    )

    # Show statistics
    term_lengths = [len(r['term']) for r in results]
    print(f"\nTerm statistics:")
    print(f"  Average length: {sum(term_lengths) / len(term_lengths):.0f} chars")
    print(f"  Min length: {min(term_lengths)} chars")
    print(f"  Max length: {max(term_lengths)} chars")
