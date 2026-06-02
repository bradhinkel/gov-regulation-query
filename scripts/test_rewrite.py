import sys
sys.path.insert(0, "/home/bradhinkel/gov-regulation-query")

from src.query import _rewrite_query

queries = [
    "What are the labeling requirements for organic produce?",
    "Who is permitted to collect samples for THC concentration level testing?",
    "What are the four main requirements that a psychiatric hospital must meet?",
]

for q in queries:
    print(f"Original:  {q}")
    print(f"Rewritten: {_rewrite_query(q)}")
    print()
