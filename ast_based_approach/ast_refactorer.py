"""
AST-Based Program Refactorer
Uses anti-unification and clone detection to extract reusable abstractions.
"""
import ast
import json
import hashlib
from collections import defaultdict, Counter
from typing import List, Tuple, Dict, Set, Optional
from dataclasses import dataclass


@dataclass
class ASTPattern:
    """Represents a recurring AST pattern."""
    tree: ast.AST
    frequency: int
    hash: str
    variables: Set[str]
    size: int  # number of nodes


class ASTNormalizer(ast.NodeTransformer):
    """Normalize AST by replacing variable names with placeholders."""

    def __init__(self):
        self.var_map = {}
        self.var_counter = 0

    def visit_Name(self, node):
        # Don't normalize built-in names
        if node.id in {'np', 'True', 'False', 'None'}:
            return node

        if node.id not in self.var_map:
            self.var_map[node.id] = f'_VAR_{self.var_counter}'
            self.var_counter += 1

        return ast.Name(id=self.var_map[node.id], ctx=node.ctx)

    def reset(self):
        self.var_map = {}
        self.var_counter = 0


def ast_to_str(node: ast.AST) -> str:
    """Convert AST node to canonical string representation."""
    return ast.unparse(node) if hasattr(ast, 'unparse') else ast.dump(node)


def ast_hash(node: ast.AST) -> str:
    """Compute hash of AST structure."""
    s = ast.dump(node, annotate_fields=False)
    return hashlib.md5(s.encode()).hexdigest()[:16]


def count_nodes(node: ast.AST) -> int:
    """Count total nodes in AST."""
    count = 1
    for child in ast.walk(node):
        if child != node:
            count += 1
    return count


class SubtreeExtractor(ast.NodeVisitor):
    """Extract all subtrees of a certain size from an AST."""

    def __init__(self, min_size=3, max_size=20):
        self.subtrees = []
        self.min_size = min_size
        self.max_size = max_size

    def visit(self, node):
        size = count_nodes(node)

        # Only consider subtrees within size bounds
        if self.min_size <= size <= self.max_size:
            # Skip trivial patterns
            if not isinstance(node, (ast.Name, ast.Constant, ast.Load, ast.Store)):
                self.subtrees.append(node)

        self.generic_visit(node)
        return node


def extract_common_subtrees(programs: List[str], min_freq=3, min_size=3) -> List[ASTPattern]:
    """
    Extract common AST subtrees across multiple programs.

    Args:
        programs: List of program source codes
        min_freq: Minimum frequency to consider a pattern
        min_size: Minimum AST node count

    Returns:
        List of recurring patterns sorted by frequency
    """
    subtree_counts = defaultdict(list)
    normalizer = ASTNormalizer()

    for prog_idx, program in enumerate(programs):
        try:
            tree = ast.parse(program)

            # Extract all subtrees
            extractor = SubtreeExtractor(min_size=min_size)
            extractor.visit(tree)

            # Normalize and hash each subtree
            for subtree in extractor.subtrees:
                normalizer.reset()
                normalized = normalizer.visit(ast.copy_location(
                    normalizer.visit(subtree), subtree
                ))

                h = ast_hash(normalized)
                subtree_counts[h].append({
                    'prog_idx': prog_idx,
                    'subtree': subtree,
                    'normalized': normalized,
                    'variables': set(normalizer.var_map.keys()),
                    'size': count_nodes(subtree)
                })
        except SyntaxError:
            continue

    # Filter by frequency and create patterns
    patterns = []
    for h, occurrences in subtree_counts.items():
        if len(occurrences) >= min_freq:
            first = occurrences[0]
            pattern = ASTPattern(
                tree=first['normalized'],
                frequency=len(occurrences),
                hash=h,
                variables=first['variables'],
                size=first['size']
            )
            patterns.append(pattern)

    # Sort by frequency * size (bigger, more common patterns first)
    patterns.sort(key=lambda p: p.frequency * p.size, reverse=True)

    return patterns


def extract_function_body_patterns(programs: List[str]) -> List[Tuple[str, int]]:
    """
    Extract common expression patterns from function bodies.
    Returns (expression_str, frequency) pairs.
    """
    expression_counts = Counter()

    for program in programs:
        try:
            tree = ast.parse(program)

            # Find all expressions in the function
            for node in ast.walk(tree):
                if isinstance(node, (ast.BinOp, ast.Compare, ast.Call, ast.BoolOp)):
                    # Get source representation
                    try:
                        expr_str = ast.unparse(node)
                        # Normalize whitespace
                        expr_str = ' '.join(expr_str.split())
                        expression_counts[expr_str] += 1
                    except:
                        pass
        except:
            continue

    # Filter and sort
    common = [(expr, count) for expr, count in expression_counts.items()
              if count >= 3 and len(expr) > 10]
    common.sort(key=lambda x: -x[1])

    return common


def identify_clone_groups(programs: List[Dict], similarity_threshold=0.8) -> Dict[str, List[int]]:
    """
    Group programs into clone families based on AST similarity.
    Returns mapping of clone_id -> list of program indices.
    """
    # Compute structural hashes for each program
    program_hashes = []

    for i, prog in enumerate(programs):
        try:
            tree = ast.parse(prog['solution'])

            # Normalize variable names
            normalizer = ASTNormalizer()
            normalized = normalizer.visit(tree)

            # Compute hash
            h = ast_hash(normalized)
            program_hashes.append((i, h))
        except:
            program_hashes.append((i, None))

    # Group by hash
    clone_groups = defaultdict(list)
    for idx, h in program_hashes:
        if h:
            clone_groups[h].append(idx)

    # Filter to only groups with multiple members
    return {h: indices for h, indices in clone_groups.items() if len(indices) > 1}


def generate_helper_from_pattern(pattern: ASTPattern, name: str) -> str:
    """Generate a helper function from an AST pattern."""

    # Get the expression
    expr_str = ast_to_str(pattern.tree)

    # Extract parameters (the variables in the pattern)
    params = sorted(pattern.variables)
    param_str = ', '.join(params) if params else ''

    # Generate function
    func_code = f'''def {name}({param_str}):
    """Auto-generated helper (frequency: {pattern.frequency}, size: {pattern.size} nodes)."""
    return {expr_str}
'''

    return func_code


def analyze_ast_patterns(programs_file: str, output_file: str):
    """Main analysis function."""

    # Load programs
    with open(programs_file, 'r') as f:
        programs = [json.loads(line) for line in f]

    print(f"Loaded {len(programs)} programs\n")

    print("="*70)
    print("STEP 1: AST SUBTREE ANALYSIS")
    print("="*70)

    solutions = [p['solution'] for p in programs]
    patterns = extract_common_subtrees(solutions, min_freq=5, min_size=4)

    print(f"\nFound {len(patterns)} recurring AST patterns\n")
    print("Top 10 patterns by frequency × size:")
    print(f"{'Rank':<6} {'Freq':<6} {'Size':<6} {'Score':<8} {'Pattern'}")
    print("-"*70)

    for i, pattern in enumerate(patterns[:10], 1):
        score = pattern.frequency * pattern.size
        expr = ast_to_str(pattern.tree)[:50]
        print(f"{i:<6} {pattern.frequency:<6} {pattern.size:<6} {score:<8} {expr}...")

    print("\n" + "="*70)
    print("STEP 2: EXPRESSION PATTERN ANALYSIS")
    print("="*70)

    expressions = extract_function_body_patterns(solutions)

    print(f"\nFound {len(expressions)} common expressions\n")
    print("Top 15 most frequent expressions:")
    print(f"{'Rank':<6} {'Freq':<6} {'Expression'}")
    print("-"*70)

    for i, (expr, freq) in enumerate(expressions[:15], 1):
        expr_short = expr[:60] + '...' if len(expr) > 60 else expr
        print(f"{i:<6} {freq:<6} {expr_short}")

    print("\n" + "="*70)
    print("STEP 3: CLONE DETECTION")
    print("="*70)

    clones = identify_clone_groups(programs)

    print(f"\nFound {len(clones)} clone groups\n")

    # Sort by group size
    clone_list = sorted(clones.items(), key=lambda x: -len(x[1]))

    print("Largest clone groups:")
    print(f"{'Rank':<6} {'Size':<6} {'Example Description'}")
    print("-"*70)

    for i, (clone_id, indices) in enumerate(clone_list[:10], 1):
        example_desc = programs[indices[0]]['description'][:50]
        print(f"{i:<6} {len(indices):<6} {example_desc}...")

    # Generate report
    report = {
        'total_programs': len(programs),
        'ast_patterns_found': len(patterns),
        'expression_patterns_found': len(expressions),
        'clone_groups_found': len(clones),
        'top_patterns': [
            {
                'frequency': p.frequency,
                'size': p.size,
                'score': p.frequency * p.size,
                'expression': ast_to_str(p.tree),
                'variables': list(p.variables)
            }
            for p in patterns[:20]
        ],
        'top_expressions': expressions[:20],
        'largest_clones': [
            {
                'size': len(indices),
                'program_indices': indices[:5],  # First 5 examples
                'example': programs[indices[0]]['description']
            }
            for _, indices in clone_list[:10]
        ]
    }

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n✓ Analysis complete. Report saved to {output_file}")

    return patterns, expressions, clones


if __name__ == '__main__':
    patterns, expressions, clones = analyze_ast_patterns(
        'battleship_programs.jsonl',
        'ast_analysis_report.json'
    )
