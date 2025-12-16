# AST-Extracted Helper Functions
import numpy as np

def get_unrevealed_mask(true_board, partial_board):
    """Returns mask of ship tiles that are not yet revealed."""
    return (true_board > 0) & (partial_board == -1)

def row_to_index(row_letter):
    """Convert row letter (A-H) to 0-based index."""
    return ord(row_letter.upper()) - ord('A')

def col_to_index(col_number):
    """Convert 1-based column number to 0-based index."""
    return col_number - 1

def has_unrevealed_in_row(true_board, partial_board, row_idx):
    """Check if row has any unrevealed ship tiles."""
    mask = (true_board[row_idx, :] > 0) & (partial_board[row_idx, :] == -1)
    return bool(np.any(mask))

def has_unrevealed_in_col(true_board, partial_board, col_idx):
    """Check if column has any unrevealed ship tiles."""
    mask = (true_board[:, col_idx] > 0) & (partial_board[:, col_idx] == -1)
    return bool(np.any(mask))

def get_ship_coords(true_board, ship_id):
    """Get all coordinates of a ship."""
    return np.argwhere(true_board == ship_id)

def is_vertical(coords):
    """Check if coordinates form a vertical line."""
    if coords.shape[0] < 2:
        return False
    return np.all(coords[:, 1] == coords[0, 1])

def is_horizontal(coords):
    """Check if coordinates form a horizontal line."""
    if coords.shape[0] < 2:
        return False
    return np.all(coords[:, 0] == coords[0, 0])
