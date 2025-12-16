#!/usr/bin/env python3
"""
Translate Stitch abstractions back to Python code.

This shows that the learned abstractions can be converted back to executable Python.
"""
import json
import re


# Translation rules for Stitch primitives to Python
PRIMITIVE_TRANSLATIONS = {
    'any': 'np.any',
    'all': 'np.all',
    'tobool': 'bool',
    'gt': '>',
    'lt': '<',
    'gte': '>=',
    'lte': '<=',
    'eq': '==',
    'ne': '!=',
    'and': '&',
    'or': '|',
    'not': 'np.logical_not',
    'add': '+',
    'sub': '-',
    'mul': '*',
    'div': '/',
    'get': 'get_index',  # Special handling needed
    'pair': 'tuple',
    'slice': 'slice',
    'unique': 'np.unique',
    'len': 'len',
}


def translate_to_python(sexp: str, abstractions: dict = None) -> str:
    """
    Translate a Stitch s-expression to Python code.

    Args:
        sexp: The s-expression to translate
        abstractions: Dict mapping fn_X names to their bodies

    Returns:
        Python code string
    """
    if abstractions is None:
        abstractions = {}

    # Parse the s-expression
    sexp = sexp.strip()

    # Handle atoms (variables, numbers, primitives)
    if not sexp.startswith('('):
        # De Bruijn index
        if sexp.startswith('#'):
            idx = int(sexp[1:])
            return f"arg{idx}"

        # Free variable
        if sexp.startswith('v'):
            return sexp  # Keep as v0, v1, etc.

        # Number
        if sexp.isdigit() or (sexp.startswith('-') and sexp[1:].isdigit()):
            return sexp

        # Boolean
        if sexp == 'true':
            return 'True'
        if sexp == 'false':
            return 'False'

        # Primitive
        if sexp in PRIMITIVE_TRANSLATIONS:
            return PRIMITIVE_TRANSLATIONS[sexp]

        # Abstraction reference
        if sexp.startswith('fn_'):
            if sexp in abstractions:
                return f"({translate_to_python(abstractions[sexp], abstractions)})"
            return sexp

        return sexp

    # Parse compound expression
    tokens = tokenize(sexp)

    if not tokens:
        return ""

    op = tokens[0]

    # Lambda abstraction
    if op == 'lam':
        body = ' '.join(tokens[1:])
        return f"lambda arg: {translate_to_python(body, abstractions)}"

    # Application
    if op == 'app':
        if len(tokens) == 2:
            # Partial application
            return translate_to_python(tokens[1], abstractions)
        elif len(tokens) == 3:
            func = translate_to_python(tokens[1], abstractions)
            arg = translate_to_python(tokens[2], abstractions)

            # Special handling for operators
            if func in ['>', '<', '>=', '<=', '==', '!=', '&', '|', '+', '-', '*', '/']:
                return f"({arg} {func})"

            # Function application
            return f"{func}({arg})"

    # Abstraction reference
    if op.startswith('fn_'):
        # Apply the abstraction to remaining args
        abs_body = abstractions.get(op, op)
        result = translate_to_python(abs_body, abstractions)

        # Apply to arguments
        for arg in tokens[1:]:
            arg_py = translate_to_python(arg, abstractions)
            result = f"{result}({arg_py})"

        return result

    return f"({' '.join(translate_to_python(t, abstractions) for t in tokens)})"


def tokenize(sexp: str) -> list:
    """Simple tokenizer for s-expressions."""
    sexp = sexp.strip()
    if not sexp.startswith('('):
        return [sexp]

    # Remove outer parens
    sexp = sexp[1:-1]

    tokens = []
    current = ""
    depth = 0

    for char in sexp:
        if char == '(':
            depth += 1
            current += char
        elif char == ')':
            depth -= 1
            current += char
        elif char == ' ' and depth == 0:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += char

    if current:
        tokens.append(current)

    return tokens


def main():
    """Translate some example abstractions and programs."""

    # Load results
    with open('results/canonical_100_iterations/results.json') as f:
        results = json.load(f)

    # Build abstraction dictionary
    abstractions = {}
    for abs_info in results['abstractions']:
        abstractions[abs_info['name']] = abs_info['body']

    print("=" * 80)
    print("TRANSLATING STITCH ABSTRACTIONS TO PYTHON")
    print("=" * 80)
    print()

    # Translate top abstractions
    print("Top 10 Abstractions:")
    print()

    for i, abs_info in enumerate(results['abstractions'][:10], 1):
        name = abs_info['name']
        body = abs_info['body']

        # Try to translate (may not be perfect for complex ones)
        try:
            python = translate_to_python(body, abstractions)
            print(f"{i:2}. {name}: {abs_info['num_uses']} uses")
            print(f"    Stitch: {body}")
            print(f"    Python: {python}")
            print()
        except Exception as e:
            print(f"{i:2}. {name}: (translation error: {e})")
            print()

    print("=" * 80)
    print("EXAMPLE: Translating Compressed Programs")
    print("=" * 80)
    print()

    # Show some rewritten programs
    print("These programs were compressed using the learned abstractions:")
    print()

    for i in [12, 14, 16]:
        original = results['original'][i]
        rewritten = results['rewritten'][i]

        print(f"Program {i}:")
        print(f"  Original:  {original}")
        print(f"  Rewritten: {rewritten}")

        # Translate the rewritten version
        if rewritten in abstractions:
            expanded = abstractions[rewritten]
            print(f"  Expanded:  {expanded}")

        print()

    print("=" * 80)
    print("NOTES ON TRANSLATION")
    print("=" * 80)
    print()
    print("1. Free variables (v0, v1, etc.) represent intermediate computations")
    print("   that need to be provided when using the abstraction")
    print()
    print("2. De Bruijn indices (#0, #1) are lambda parameters - translate to")
    print("   actual parameter names in the lambda")
    print()
    print("3. The abstractions form a LIBRARY of reusable patterns that can be")
    print("   composed together to build complex programs")
    print()
    print("4. Full reconstruction would require:")
    print("   - Tracking what v0, v1, etc. represent in each program")
    print("   - Inlining all abstraction definitions")
    print("   - Converting lambda calculus to imperative Python")


if __name__ == '__main__':
    main()