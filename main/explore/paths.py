"""Locate the Blockstream SPHINCS-Parameters checkout (see setup_upstream.sh).

Override with the environment variable SPHINCS_PARAMS.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM = os.environ.get(
    'SPHINCS_PARAMS',
    os.path.join(HERE, 'third_party', 'SPHINCS-Parameters'))
if not os.path.isdir(os.path.join(UPSTREAM, 'tests')):
    sys.exit(f'SPHINCS-Parameters not found at {UPSTREAM}; run ./setup_upstream.sh first')
for sub in ('tests', 'third_party'):
    p = os.path.join(UPSTREAM, sub)
    if p not in sys.path:
        sys.path.insert(0, p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
