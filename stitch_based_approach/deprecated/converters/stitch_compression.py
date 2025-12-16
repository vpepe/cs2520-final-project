"""
Stitch-style compression for Python programs.

Implements core ideas from "Bottom-Up Synthesis of Recursive Functional Programs
using Angelic Execution" (Stitch paper by Bowers et al., 2023).

Key concepts:
1. Anti-unification: Find most general generalization of two terms
2. Compression: Extract abstractions that minimize total program size
3. Iteration: Repeatedly find and extract common patterns
"""
import json
from typing import List, Tuple, Dict, Set
from dataclasses import dataclass
from collections import defaultdict
from python_to_terms import Term, python_to_term, extract_function_body_term


@dataclass
class Abstraction:
    """A discovered abstraction (library function)."""
    name: str
    params: List[str]
    body: Term
    usages: int
    compression_gain: int  # How many chars saved by using this


class StitchCompressor:
    """Implements Stitch-style compression via anti-unification."""

    def __init__(self):
        self.abstractions = []
        self.abstraction_counter = 0

    def anti_unify(self, t1: Term, t2: Term) -> Tuple[Term, Dict[str, Term], Dict[str, Term]]:
        """
        Anti-unify two terms to find their most general generalization.

        Returns:
            (generalized_term, substitution1, substitution2)

        Example:
            anti_unify((+ 1 2), (+ 3 4))
            => ((+ ?x ?y), {?x: 1, ?y: 2}, {?x: 3, ?y: 4})
        """
        if t1.op != t2.op:
            # Different operators -> create fresh variable
            var_name = f"?v{self.abstraction_counter}"
            self.abstraction_counter += 1
            return (
                Term('var', [var_name]),
                {var_name: t1},
                {var_name: t2}
            )

        if len(t1.args) != len(t2.args):
            # Different arity -> create fresh variable
            var_name = f"?v{self.abstraction_counter}"
            self.abstraction_counter += 1
            return (
                Term('var', [var_name]),
                {var_name: t1},
                {var_name: t2}
            )

        # Same operator -> recursively anti-unify arguments
        gen_args = []
        sub1 = {}
        sub2 = {}

        for arg1, arg2 in zip(t1.args, t2.args):
            if isinstance(arg1, Term) and isinstance(arg2, Term):
                gen_arg, s1, s2 = self.anti_unify(arg1, arg2)
                gen_args.append(gen_arg)
                sub1.update(s1)
                sub2.update(s2)
            elif arg1 == arg2:
                # Identical primitive arguments
                gen_args.append(arg1)
            else:
                # Different primitives -> create variable
                var_name = f"?v{self.abstraction_counter}"
                self.abstraction_counter += 1
                gen_args.append(Term('var', [var_name]))
                sub1[var_name] = arg1
                sub2[var_name] = arg2

        return Term(t1.op, gen_args), sub1, sub2

    def find_common_subterm(self, terms: List[Term], min_size: int = 10) -> Tuple[Term, List[int]]:
        """
        Find the most compressible common subterm across all terms.

        Returns:
            (generalized_subterm, list_of_term_indices_containing_it)
        """
        # Extract all subterms from all terms
        all_subterms = []
        for idx, term in enumerate(terms):
            subterms = self._extract_subterms(term)
            for sub in subterms:
                if len(sub.to_sexp()) >= min_size:
                    all_subterms.append((sub, idx))

        if not all_subterms:
            return None, []

        # Try anti-unifying pairs and track compression gain
        best_abstraction = None
        best_gain = 0
        best_indices = []

        for i, (sub1, idx1) in enumerate(all_subterms):
            matching_indices = {idx1}
            generalizations = []

            for sub2, idx2 in all_subterms[i+1:]:
                gen, s1, s2 = self.anti_unify(sub1, sub2)

                # Calculate compression gain
                # Gain = (size(sub1) + size(sub2)) - (size(gen) + overhead)
                original_size = len(sub1.to_sexp()) + len(sub2.to_sexp())
                generalized_size = len(gen.to_sexp())
                overhead = 20  # Approximate overhead for function definition

                gain = original_size - generalized_size - overhead

                if gain > 0 and len(s1) <= 3:  # Limit parameters to keep it simple
                    generalizations.append((gen, idx2, gain))

            # Find best generalization for this subterm
            for gen, idx2, gain in generalizations:
                total_indices = matching_indices | {idx2}
                total_gain = gain * len(total_indices)

                if total_gain > best_gain:
                    best_gain = total_gain
                    best_abstraction = gen
                    best_indices = list(total_indices)

        return best_abstraction, best_indices

    def _extract_subterms(self, term: Term) -> List[Term]:
        """Extract all subterms from a term."""
        subterms = [term]

        for arg in term.args:
            if isinstance(arg, Term):
                subterms.extend(self._extract_subterms(arg))

        return subterms

    def compress_programs(self, programs: List[Dict], iterations: int = 5) -> List[Abstraction]:
        """
        Run Stitch-style compression on programs.

        Args:
            programs: List of programs with 'term' field
            iterations: Number of compression iterations

        Returns:
            List of discovered abstractions
        """
        # Parse terms
        terms = []
        for prog in programs:
            try:
                # Parse the s-expression back to Term
                # For simplicity, we'll use the function body directly
                term = extract_function_body_term(prog['original_code'])
                terms.append(term)
            except:
                continue

        print(f"Compressing {len(terms)} programs...")

        # Iteratively find and extract abstractions
        for iteration in range(iterations):
            print(f"\nIteration {iteration + 1}/{iterations}")

            # Find best abstraction
            gen_term, indices = self.find_common_subterm(terms)

            if gen_term is None or len(indices) < 2:
                print("  No more profitable abstractions found")
                break

            # Extract parameters from generalized term
            params = self._extract_params(gen_term)

            # Create abstraction
            abs_name = f"helper_{len(self.abstractions)}"
            abstraction = Abstraction(
                name=abs_name,
                params=params,
                body=gen_term,
                usages=len(indices),
                compression_gain=len(indices) * 50  # Approximate
            )

            self.abstractions.append(abstraction)

            print(f"  Found abstraction: {abs_name}")
            print(f"    Parameters: {params}")
            print(f"    Used in {len(indices)} programs")
            print(f"    Body: {gen_term.to_sexp()[:80]}...")

        print(f"\nDiscovered {len(self.abstractions)} abstractions")
        return self.abstractions

    def _extract_params(self, term: Term) -> List[str]:
        """Extract parameter names from a generalized term."""
        params = set()

        def collect_vars(t):
            if isinstance(t, Term):
                if t.op == 'var' and t.args and str(t.args[0]).startswith('?'):
                    params.add(t.args[0])
                for arg in t.args:
                    collect_vars(arg)

        collect_vars(term)
        return sorted(params)

    def generate_library(self) -> str:
        """Generate Python code for the discovered library."""
        code = "# Stitch-Discovered Helper Library\n"
        code += "import numpy as np\n\n"

        for abs in self.abstractions:
            # Convert term back to Python (simplified)
            params_str = ', '.join(abs.params)
            body_comment = abs.body.to_sexp()[:100]

            code += f"def {abs.name}({params_str}):\n"
            code += f'    """\n'
            code += f'    Auto-discovered by Stitch compression.\n'
            code += f'    Used in {abs.usages} programs.\n'
            code += f'    Pattern: {body_comment}...\n'
            code += f'    """\n'
            code += f'    # TODO: Implement based on pattern\n'
            code += f'    pass\n\n'

        return code


def analyze_term_patterns(programs: List[Dict]):
    """Analyze patterns in term representations."""

    # Count term operators
    op_counts = defaultdict(int)
    term_hashes = defaultdict(list)

    for prog in programs:
        term_str = prog['term']

        # Count operators
        for op in ['assign', 'return', 'call', 'gt', 'eq', 'bitand', 'subscript']:
            op_counts[op] += term_str.count(f'({op} ')

        # Hash normalized terms
        normalized = term_str.replace('?v0', '?x').replace('?v1', '?y')
        term_hashes[normalized].append(prog['id'])

    print("Term operator frequency:")
    for op, count in sorted(op_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {op:15s}: {count:4d}")

    print(f"\nUnique term patterns: {len(term_hashes)}")
    print("\nMost common patterns:")
    for i, (pattern, progs) in enumerate(sorted(term_hashes.items(), key=lambda x: -len(x[1]))[:5], 1):
        print(f"  {i}. Appears in {len(progs)} programs")
        print(f"     Pattern: {pattern[:100]}...")


def main():
    """Main Stitch compression pipeline."""

    print("="*70)
    print("STITCH-STYLE COMPRESSION FOR PYTHON PROGRAMS")
    print("="*70)

    # Load terms
    with open('programs_as_terms.json', 'r') as f:
        programs = json.load(f)

    print(f"\nLoaded {len(programs)} programs as terms\n")

    # Analyze patterns
    print("="*70)
    print("PATTERN ANALYSIS")
    print("="*70)
    analyze_term_patterns(programs)

    # Run compression
    print("\n" + "="*70)
    print("COMPRESSION")
    print("="*70)

    compressor = StitchCompressor()
    abstractions = compressor.compress_programs(programs, iterations=10)

    # Generate library
    print("\n" + "="*70)
    print("LIBRARY GENERATION")
    print("="*70)

    library_code = compressor.generate_library()

    with open('stitch_library.py', 'w') as f:
        f.write(library_code)

    print(f"Generated library with {len(abstractions)} helpers")
    print("Saved to: stitch_library.py")

    # Save results
    results = {
        'abstractions_found': len(abstractions),
        'abstractions': [
            {
                'name': a.name,
                'params': a.params,
                'body': a.body.to_sexp(),
                'usages': a.usages,
                'compression_gain': a.compression_gain
            }
            for a in abstractions
        ]
    }

    with open('stitch_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "="*70)
    print("✓ Stitch compression complete")
    print("="*70)


if __name__ == '__main__':
    main()
