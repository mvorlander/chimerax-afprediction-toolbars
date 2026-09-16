"""Array operations for confidence filtering; no Qt or ChimeraX dependencies."""
import numpy as np


def interchain_mask(matrix, chains, cutoff, chain_pair=None, include_cells=True):
    """Select both endpoints of directed PAE contacts, in bounded-size blocks.

    Negative chain codes denote invalid/deleted rows. Do not cache matrix results:
    callers may edit PAE data or delete residues between successive operations.
    """
    size = len(chains)
    chains = np.asarray(chains)
    selected = np.zeros(size, dtype=bool)
    cells = np.zeros((size, size), dtype=bool) if include_cells else None
    for start in range(0, size, 128):
        stop = min(start + 128, size)
        a, b = chains[start:stop, None], chains[None, :]
        block = np.less(matrix[start:stop, :size].astype(np.float64, copy=False), cutoff)
        block &= (a >= 0) & (b >= 0) & (a != b)
        if chain_pair is not None:
            first, second = chain_pair
            block &= ((a == first) & (b == second)) | ((a == second) & (b == first))
        selected[start:stop] |= block.any(axis=1)
        selected |= block.any(axis=0)
        if cells is not None:
            cells[start:stop] = block
    return selected, cells


def selection_masks(selected, chains, interchain_only=False):
    """Manual selection stripes and intersections without Python cell tuples."""
    selected = np.asarray(selected, dtype=bool)
    chains = np.asarray(chains)
    cells = selected[:, None] | selected[None, :]
    emphasis = selected[:, None] & selected[None, :]
    if interchain_only:
        for start in range(0, len(chains), 128):
            a, b = chains[start:start + 128, None], chains[None, :]
            allowed = (a >= 0) & (b >= 0) & (a != b)
            cells[start:start + 128] &= allowed
            emphasis[start:start + 128] &= allowed
    return cells, emphasis


def overlay_indices(mask, emphasis=None):
    """One indexed-color image, with exact cell coverage and a cell-wide outline."""
    pixels = np.zeros(mask.shape, dtype=np.uint8)
    def paint(cells, fill, outline):
        pixels[cells] = fill
        # Interior needs all four neighbours; no wrapping across image edges.
        interior = cells.copy()
        interior[0, :] = interior[-1, :] = False
        interior[:, 0] = interior[:, -1] = False
        interior[1:, :] &= cells[:-1, :]
        interior[:-1, :] &= cells[1:, :]
        interior[:, 1:] &= cells[:, :-1]
        interior[:, :-1] &= cells[:, 1:]
        pixels[cells & ~interior] = outline
    if mask.size:
        paint(mask, 1, 2)
        if emphasis is not None:
            paint(emphasis, 3, 4)
    return pixels
