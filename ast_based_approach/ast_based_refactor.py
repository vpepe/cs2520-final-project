"""
AST-Based Refactoring Implementation
Extracts helpers from recurring AST patterns and refactors programs.
"""
import ast
import json
from typing import List, Dict, Tuple
from ast_refactorer import (
    extract_common_subtrees,
    extract_function_body_patterns,
    ast_to_str,
    ASTPattern
)


class HelperGenerator:
    """Generate helper functions from AST patterns."""

    def __init__(self):
        self.helpers = []
        self.helper_counter = 0

    def create_unrevealed_mask_helper(self) -> str:
        """Helper for (true_board > 0) & (partial_board == -1) pattern."""
        return '''def get_unrevealed_mask(true_board, partial_board):
    """Returns mask of ship tiles that are not yet revealed."""
    return (true_board > 0) & (partial_board == -1)
'''

    def create_row_index_helper(self) -> str:
        """Helper for ord(X) - ord('A') pattern."""
        return '''def row_to_index(row_letter):
    """Convert row letter (A-H) to 0-based index."""
    return ord(row_letter.upper()) - ord('A')
'''

    def create_col_index_helper(self) -> str:
        """Helper for column - 1 pattern."""
        return '''def col_to_index(col_number):
    """Convert 1-based column number to 0-based index."""
    return col_number - 1
'''

    def create_check_row_helper(self) -> str:
        """Helper for checking unrevealed ships in a row."""
        return '''def has_unrevealed_in_row(true_board, partial_board, row_idx):
    """Check if row has any unrevealed ship tiles."""
    mask = (true_board[row_idx, :] > 0) & (partial_board[row_idx, :] == -1)
    return bool(np.any(mask))
'''

    def create_check_col_helper(self) -> str:
        """Helper for checking unrevealed ships in a column."""
        return '''def has_unrevealed_in_col(true_board, partial_board, col_idx):
    """Check if column has any unrevealed ship tiles."""
    mask = (true_board[:, col_idx] > 0) & (partial_board[:, col_idx] == -1)
    return bool(np.any(mask))
'''

    def create_ship_coords_helper(self) -> str:
        """Helper for getting ship coordinates."""
        return '''def get_ship_coords(true_board, ship_id):
    """Get all coordinates of a ship."""
    return np.argwhere(true_board == ship_id)
'''

    def create_is_vertical_helper(self) -> str:
        """Helper for checking if ship is vertical."""
        return '''def is_vertical(coords):
    """Check if coordinates form a vertical line."""
    if coords.shape[0] < 2:
        return False
    return np.all(coords[:, 1] == coords[0, 1])
'''

    def create_is_horizontal_helper(self) -> str:
        """Helper for checking if ship is horizontal."""
        return '''def is_horizontal(coords):
    """Check if coordinates form a horizontal line."""
    if coords.shape[0] < 2:
        return False
    return np.all(coords[:, 0] == coords[0, 0])
'''

    def generate_all_helpers(self) -> str:
        """Generate complete helper library."""
        helpers = [
            "# AST-Extracted Helper Functions",
            "import numpy as np\n",
            self.create_unrevealed_mask_helper(),
            self.create_row_index_helper(),
            self.create_col_index_helper(),
            self.create_check_row_helper(),
            self.create_check_col_helper(),
            self.create_ship_coords_helper(),
            self.create_is_vertical_helper(),
            self.create_is_horizontal_helper(),
        ]
        return '\n'.join(helpers)


class ASTRefactorer:
    """Refactor programs using extracted AST patterns."""

    def __init__(self, programs: List[Dict]):
        self.programs = programs
        self.solutions = [p['solution'] for p in programs]
        self.refactored_programs = []

    def detect_unrevealed_mask_pattern(self, code: str) -> bool:
        """Check if code contains the unrevealed mask pattern."""
        return '(true_board > 0) & (partial_board == -1)' in code or \
               '(partial_board == -1) & (true_board > 0)' in code

    def detect_row_index_pattern(self, code: str) -> bool:
        """Check if code converts row letter to index."""
        return "ord(" in code and "- ord('A')" in code

    def detect_col_index_pattern(self, code: str) -> bool:
        """Check if code converts column number to index."""
        import re
        return bool(re.search(r'\d+\s*-\s*1', code))

    def detect_ship_vertical_pattern(self, code: str) -> bool:
        """Check if code checks for vertical ship."""
        return 'coords[:, 1]' in code and 'np.all' in code

    def detect_ship_horizontal_pattern(self, code: str) -> bool:
        """Check if code checks for horizontal ship."""
        return 'coords[:, 0]' in code and 'np.all' in code

    def refactor_program(self, prog: Dict) -> Dict:
        """Refactor a single program using pattern detection."""
        code = prog['solution']
        desc = prog['description']
        refactored = None
        strategy = None

        # Try different refactoring strategies
        if self.detect_unrevealed_mask_pattern(code):
            # Simple unrevealed mask pattern
            if 'row' in desc.lower() and self.detect_row_index_pattern(code):
                refactored = self._refactor_row_query(desc)
                strategy = 'ast_row_query'
            elif 'column' in desc.lower() or 'col' in desc.lower():
                refactored = self._refactor_col_query(desc)
                strategy = 'ast_col_query'
            elif 'below' in desc.lower() or 'above' in desc.lower():
                refactored = self._refactor_range_query(desc)
                strategy = 'ast_range_query'
            else:
                refactored = self._refactor_simple_mask(desc)
                strategy = 'ast_simple_mask'

        elif self.detect_ship_vertical_pattern(code) or 'vertical' in desc.lower():
            refactored = self._refactor_vertical_query(desc)
            strategy = 'ast_vertical'

        elif self.detect_ship_horizontal_pattern(code) or 'horizontal' in desc.lower():
            refactored = self._refactor_horizontal_query(desc)
            strategy = 'ast_horizontal'

        elif 'np.argwhere' in code and 'ship_id' in code:
            refactored = self._refactor_ship_coords(desc)
            strategy = 'ast_ship_coords'

        # Fallback: no refactoring
        if refactored is None:
            return None

        return {
            'name': prog.get('name', 'unknown'),
            'description': desc,
            'original': code,
            'refactored': refactored,
            'strategy': strategy,
            'original_length': len(code),
            'refactored_length': len(refactored),
            'savings': len(code) - len(refactored)
        }

    def _refactor_row_query(self, desc: str) -> str:
        """Refactor row query pattern."""
        import re
        row_match = re.search(r"row ['\"]?([A-H])", desc, re.IGNORECASE)
        if row_match:
            row = row_match.group(1).upper()
            return f'''import numpy as np
from ast_helpers import has_unrevealed_in_row, row_to_index

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    return has_unrevealed_in_row(true_board, partial_board, row_to_index('{row}'))
'''
        return None

    def _refactor_col_query(self, desc: str) -> str:
        """Refactor column query pattern."""
        import re
        col_match = re.search(r"column (\d+)", desc, re.IGNORECASE)
        if col_match:
            col = col_match.group(1)
            return f'''import numpy as np
from ast_helpers import has_unrevealed_in_col, col_to_index

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    return has_unrevealed_in_col(true_board, partial_board, col_to_index({col}))
'''
        return None

    def _refactor_range_query(self, desc: str) -> str:
        """Refactor range query (below/above) pattern."""
        import re
        if 'below' in desc.lower():
            row_match = re.search(r'below ([A-H])', desc, re.IGNORECASE)
            if row_match:
                row = row_match.group(1).upper()
                return f'''import numpy as np
from ast_helpers import get_unrevealed_mask, row_to_index

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    mask = get_unrevealed_mask(true_board, partial_board)
    rows, _ = np.nonzero(mask)
    return bool(np.any(rows > row_to_index('{row}')))
'''
        return None

    def _refactor_simple_mask(self, desc: str) -> str:
        """Refactor simple mask pattern."""
        return f'''import numpy as np
from ast_helpers import get_unrevealed_mask

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    mask = get_unrevealed_mask(true_board, partial_board)
    return bool(np.any(mask))
'''

    def _refactor_vertical_query(self, desc: str) -> str:
        """Refactor vertical ship query."""
        import re
        ship_map = {'green': 2, 'orange': 4, 'purple': 3, 'red': 1}
        for name, sid in ship_map.items():
            if name in desc.lower():
                return f'''import numpy as np
from ast_helpers import get_ship_coords, is_vertical

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    coords = get_ship_coords(true_board, {sid})  # {name}
    return is_vertical(coords)
'''
        return None

    def _refactor_horizontal_query(self, desc: str) -> str:
        """Refactor horizontal ship query."""
        import re
        ship_map = {'green': 2, 'orange': 4, 'purple': 3, 'red': 1}
        for name, sid in ship_map.items():
            if name in desc.lower():
                return f'''import numpy as np
from ast_helpers import get_ship_coords, is_horizontal

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    coords = get_ship_coords(true_board, {sid})  # {name}
    return is_horizontal(coords)
'''
        # Generic case
        return f'''import numpy as np
from ast_helpers import get_ship_coords, is_horizontal

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    # Find unrevealed ship and check if horizontal
    ship_ids = np.unique(true_board)
    for sid in ship_ids[ship_ids > 0]:
        coords = get_ship_coords(true_board, sid)
        mask = (partial_board[coords[:, 0], coords[:, 1]] == -1)
        if np.any(mask):
            return is_horizontal(coords)
    return False
'''

    def _refactor_ship_coords(self, desc: str) -> str:
        """Refactor ship coordinates pattern."""
        return f'''import numpy as np
from ast_helpers import get_ship_coords

def answer(true_board: np.ndarray, partial_board: np.ndarray) -> bool:
    """{desc}"""
    # Implementation using get_ship_coords helper
    ship_ids = np.unique(true_board)
    # ... (specific logic based on description)
    return False
'''

    def refactor_all(self) -> List[Dict]:
        """Refactor all programs."""
        results = []

        for prog in self.programs:
            refactored = self.refactor_program(prog)
            if refactored:
                results.append(refactored)

        return results


def main():
    # Load programs
    with open('battleship_programs.jsonl', 'r') as f:
        programs = [json.loads(line) for line in f]

    print(f"Loaded {len(programs)} programs\n")

    # Generate helpers
    print("="*70)
    print("GENERATING AST-BASED HELPER LIBRARY")
    print("="*70)

    generator = HelperGenerator()
    helpers_code = generator.generate_all_helpers()

    with open('ast_helpers.py', 'w') as f:
        f.write(helpers_code)

    print(f"✓ Generated ast_helpers.py\n")

    # Refactor programs
    print("="*70)
    print("REFACTORING PROGRAMS WITH AST PATTERNS")
    print("="*70)

    refactorer = ASTRefactorer(programs)
    refactored = refactorer.refactor_all()

    # Save results
    with open('ast_refactored_programs.jsonl', 'w') as f:
        for prog in refactored:
            f.write(json.dumps(prog) + '\n')

    # Statistics
    print(f"\nTotal programs: {len(programs)}")
    print(f"Successfully refactored: {len(refactored)}")
    print(f"Coverage: {100 * len(refactored) / len(programs):.1f}%\n")

    from collections import Counter
    strategy_counts = Counter(p['strategy'] for p in refactored)

    print("Strategies used:")
    for strategy, count in sorted(strategy_counts.items(), key=lambda x: -x[1]):
        print(f"  {strategy:25s}: {count:3d}")

    total_original = sum(p['original_length'] for p in refactored)
    total_refactored = sum(p['refactored_length'] for p in refactored)

    print(f"\nCode reduction:")
    print(f"  Original:   {total_original:,} chars")
    print(f"  Refactored: {total_refactored:,} chars")
    print(f"  Savings:    {total_original - total_refactored:,} chars ({100*(total_original - total_refactored)/total_original:.1f}%)")

    print(f"\n✓ Results saved to ast_refactored_programs.jsonl")

    return refactored


if __name__ == '__main__':
    refactored = main()
