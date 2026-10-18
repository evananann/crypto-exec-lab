"""Read-only report size and duplicate-byte inventory. Never deletes evidence."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def inspect(root):
    sizes, groups, records = defaultdict(int), defaultdict(list), []
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('artifact tree contains symlink')
        if not path.is_file():
            continue
        size = path.stat().st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        name = str(path.relative_to(root))
        records.append({'path':name,'bytes':size,'sha256':digest})
        sizes[path.suffix or '(no extension)'] += size
        groups[(digest,size)].append(name)
    return {'files':len(records),'total_bytes':sum(r['bytes'] for r in records),
            'bytes_by_suffix':dict(sorted(sizes.items())),
            'largest_files':sorted(records,key=lambda r:(-r['bytes'],r['path']))[:15],
            'identical_byte_groups':[{'sha256':digest,'bytes_per_copy':size,'paths':names}
                                    for (digest,size),names in groups.items() if len(names)>1],
            'policy':'Inventory only. Keep original archives, receipts, completion inventories and frozen-source evidence. Identical bytes do not imply redundant provenance. No automatic deletion.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('reports'))
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.resolve().is_relative_to(args.root.resolve()):
        parser.error('choose new output outside the measured tree')
    result = inspect(args.root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(f'Inventoried {result["files"]} files and {result["total_bytes"]} bytes; deleted nothing')


if __name__=='__main__':
    main()
