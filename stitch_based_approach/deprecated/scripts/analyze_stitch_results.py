"""
Analyze Stitch compression results and generate refactored Python code.
"""
import json
import re
from typing import List, Dict


def parse_stitch_output(output_file: str) -> Dict:
    """Parse Stitch output JSON."""
    with open(output_file, 'r') as f:
        return json.load(f)


def sexp_to_python_sketch(sexp: str, abstraction_name: str) -> str:
    """
    Convert a Stitch s-expression abstraction to Python code sketch.

    This is a rough conversion - the actual implementation would need
    to be filled in based on the pattern.
    """
    # Count arity from #0, #1, etc.
    arity = 0
    for i in range(10):
        if f'#{i}' in sexp:
            arity = i + 1

    params = ', '.join(f'arg{i}' for i in range(arity))

    code = f"""def {abstraction_name}({params}):
    \"\"\"
    Stitch-discovered abstraction.
    Pattern: {sexp[:100]}...
    \"\"\"
    # TODO: Implement based on pattern
    pass
"""
    return code


def generate_stitch_library(stitch_output: Dict) -> str:
    """Generate Python library from Stitch abstractions."""

    code = "# Stitch-Discovered Helper Library\n"
    code += "# Auto-generated from compression results\n"
    code += "import numpy as np\n\n"

    if 'inventions' not in stitch_output:
        code += "# No abstractions discovered\n"
        return code

    for inv in stitch_output['inventions']:
        name = inv.get('name', 'helper')
        body = inv.get('body', '')
        arity = inv.get('arity', 0)
        uses = inv.get('uses', 0)

        params = ', '.join(f'arg{i}' for i in range(arity))

        code += f"def {name}({params}):\n"
        code += f'    """\n'
        code += f'    Discovered by Stitch compression.\n'
        code += f'    Used in {uses} programs.\n'
        code += f'    Arity: {arity}\n'
        code += f'    Pattern: {body[:80]}...\n'
        code += f'    """\n'
        code += f'    # Implementation would be derived from:\n'
        code += f'    # {body}\n'
        code += f'    pass\n\n'

    return code


def analyze_compression_results(iterations: List[int]):
    """Analyze Stitch results for different iteration counts."""

    print("="*70)
    print("STITCH COMPRESSION RESULTS ANALYSIS")
    print("="*70)
    print()

    results_summary = []

    for iter_count in iterations:
        output_dir = f"stitch_output_iter_{iter_count}"
        output_file = f"{output_dir}/out.json"

        try:
            with open(output_file, 'r') as f:
                data = json.load(f)

            inventions = data.get('inventions', [])

            summary = {
                'iterations': iter_count,
                'inventions_found': len(inventions),
                'original_cost': data.get('original_cost', 0),
                'final_cost': data.get('final_cost', 0),
                'compression_ratio': None
            }

            if summary['original_cost'] > 0:
                summary['compression_ratio'] = summary['original_cost'] / summary['final_cost']

            results_summary.append(summary)

            print(f"Iterations: {iter_count}")
            print(f"  Inventions found: {len(inventions)}")
            print(f"  Original cost:    {summary['original_cost']}")
            print(f"  Final cost:       {summary['final_cost']}")
            if summary['compression_ratio']:
                print(f"  Compression:      {summary['compression_ratio']:.2f}x")

            # Generate library for this iteration count
            library_code = generate_stitch_library(data)
            library_file = f"{output_dir}/stitch_library.py"

            with open(library_file, 'w') as f:
                f.write(library_code)

            print(f"  Library saved to: {library_file}")
            print()

        except FileNotFoundError:
            print(f"Iterations: {iter_count}")
            print(f"  Results not found at {output_file}")
            print()
        except Exception as e:
            print(f"Iterations: {iter_count}")
            print(f"  Error analyzing results: {e}")
            print()

    # Generate comparison report
    print("="*70)
    print("COMPARISON ACROSS ITERATIONS")
    print("="*70)
    print()

    print(f"{'Iterations':<12} {'Inventions':<12} {'Original':<12} {'Final':<12} {'Compression':<12}")
    print("-"*70)

    for summary in results_summary:
        comp_str = f"{summary['compression_ratio']:.2f}x" if summary['compression_ratio'] else "N/A"
        print(f"{summary['iterations']:<12} {summary['inventions_found']:<12} "
              f"{summary['original_cost']:<12} {summary['final_cost']:<12} {comp_str:<12}")

    # Save summary
    with open('stitch_compression_summary.json', 'w') as f:
        json.dump(results_summary, f, indent=2)

    print()
    print("✓ Analysis complete")
    print("✓ Summary saved to stitch_compression_summary.json")


def create_readme():
    """Create README for Stitch-based approach."""

    readme = """# Stitch-Based Refactoring Approach

This approach uses the actual Stitch tool (Bowers et al., POPL 2023) for program compression via anti-unification.

## What is Stitch?

Stitch is a tool for discovering reusable abstractions in programs through compression. It uses:
- **Anti-unification**: Finding the most general generalization of program patterns
- **Compression-driven search**: Optimizing for minimal total program size
- **Lambda calculus**: Working at the level of terms, not raw syntax

Paper: [Top-Down Synthesis For Library Learning](https://arxiv.org/abs/2211.16605)

## Pipeline

1. **Python → Lambda Calculus**: Convert Battleship programs to s-expressions
2. **Stitch Compression**: Run Stitch to discover abstractions
3. **Analysis**: Extract discovered patterns and generate helpers
4. **Refactoring**: Apply abstractions back to Python programs

## Files

- `python_to_stitch.py` - Convert Python AST to Stitch s-expressions
- `run_stitch.sh` - Run Stitch compression pipeline
- `analyze_stitch_results.py` - Analyze compression results
- `stitch/` - Actual Stitch implementation (Rust)
- `battleship_for_stitch.json` - Programs in Stitch format
- `stitch_output_iter_*/` - Results for different iteration counts

## Usage

```bash
# Convert programs to Stitch format
python3 python_to_stitch.py

# Run Stitch compression (requires Rust/Cargo)
./run_stitch.sh

# Analyze results
python3 analyze_stitch_results.py
```

## Advantages over Pattern/AST Approaches

✓ **Theoretically principled** - based on compression theory
✓ **Provably optimal** - finds compression-optimal abstractions
✓ **No domain knowledge** - works on any lambda calculus programs
✓ **Research-validated** - published at POPL 2023
✓ **Language-agnostic** - works on DSLs, not just Python

## Challenges

✗ **Lambda calculus gap** - Python semantics don't map cleanly
✗ **Imperative code** - Stitch designed for functional programs
✗ **Array operations** - numpy primitives need careful encoding
✗ **Higher abstraction level** - may miss low-level Python idioms

## Relation to Other Approaches

**vs Pattern-Based**: More principled, but may miss domain-specific patterns
**vs AST-Based**: Works on semantics (terms) not syntax (ASTs)
**vs Librarian**: Sound, complete, and deterministic

## Expected Results

Stitch should discover abstractions like:
- Common mask operations: `(and (gt board 0) (eq board -1))`
- Index conversions: `(sub (ord x) (ord 'A'))`
- Boolean reductions: `(bool (np-any ...))`

These will be at a higher level of abstraction than the pattern/AST approaches.
"""

    with open('README.md', 'w') as f:
        f.write(readme)

    print("✓ README created")


if __name__ == '__main__':
    # Analyze results for different iteration counts
    analyze_compression_results([1, 3, 5, 10])

    # Create README
    create_readme()
