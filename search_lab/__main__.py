"""python -m search_lab [--seed | --evaluate]; serving itself never seeds a database."""

import argparse
import json
import os
import sys

import uvicorn

from .config import LabError, load_config
from .service import Lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--seed", action="store_true", help="Explicit scoped insert-only seed and IVF index creation")
    group.add_argument("--evaluate", action="store_true", help="Run all eight cases with three warm repeats")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    args = parser.parse_args()
    if not args.seed and not args.evaluate:
        from .app import hosting

        cloud, _, _ = hosting()
        uvicorn.run(
            "search_lab.app:app",
            host="0.0.0.0" if cloud else "127.0.0.1",
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )
        return 0
    lab = None
    try:
        c = load_config().validate(writes=args.seed)
        lab = Lab(c)
        lab.load(allow_new=args.seed)
        if args.seed:
            result = lab.db.seed(lab.records)
        else:
            result = [lab.evaluate_case(q["id"]) for q in lab.queries]
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except LabError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception:
        print(
            "Managed Azure operation failed; no cleanup or fallback performed. Check configuration and permissions.",
            file=sys.stderr,
        )
        return 1
    finally:
        if lab:
            lab.close()


if __name__ == "__main__":
    raise SystemExit(main())
