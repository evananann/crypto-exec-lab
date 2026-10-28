"""Execute the walkthrough locally or without a checkout; optional notebook tools."""
from __future__ import annotations
import argparse
from pathlib import Path
import tempfile


def execute(output, *, kernel='python3', detached=False):
    import nbformat
    from nbclient import NotebookClient
    root = Path(__file__).resolve().parents[1]
    nb = nbformat.read(root/'notebooks/01_thesis_walkthrough.ipynb', as_version=4)
    for cell in nb.cells:
        if cell.cell_type == 'code':
            cell.outputs = []
            cell.execution_count = None
    with tempfile.TemporaryDirectory(prefix='cel-notebook-') as temporary:
        cwd = temporary if detached else str(root)
        NotebookClient(nb, timeout=120, kernel_name=kernel, resources={'metadata': {'path': cwd}}).execute()
    output.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, output)
    return {'executed_code_cells': sum(c.cell_type == 'code' for c in nb.cells),
            'detached_embedded_fallback': detached, 'synthetic': True, 'market_tapes_read': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kernel', default='python3')
    parser.add_argument('--detached', action='store_true')
    args = parser.parse_args()
    print(execute(args.output, kernel=args.kernel, detached=args.detached))
