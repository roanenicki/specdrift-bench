"""Command line interface: python -m invlite.cli <command> ..."""
import argparse
import sys

from invlite.io import load_csv, save_csv
from invlite.models import AppError
from invlite.store import InventoryStore


def echo(text=""):
    sys.stdout.write(f"{text}\n")


def _load(path):
    try:
        return load_csv(path)
    except FileNotFoundError:
        return InventoryStore()


def cmd_add(args):
    store = _load(args.db)
    store.add_item(args.sku, args.name, args.qty, args.price)
    save_csv(store, args.db)
    echo(f"added {args.sku}")


def cmd_list(args):
    store = _load(args.db)
    for item in store.list_items():
        echo(f"{item.sku}\t{item.name}\t{item.qty}\t{item.price:.2f}")


def cmd_value(args):
    store = _load(args.db)
    echo(f"{store.total_value():.2f}")


def cmd_report(args):
    from legacy.old_report import build_report

    store = _load(args.db)
    echo(build_report(store.list_items()))


def build_parser():
    parser = argparse.ArgumentParser(prog="invlite")
    parser.add_argument("--db", default="inventory.csv")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("sku")
    p_add.add_argument("name")
    p_add.add_argument("qty", type=int)
    p_add.add_argument("price", type=float)
    p_add.set_defaults(func=cmd_add)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("value").set_defaults(func=cmd_value)
    sub.add_parser("report").set_defaults(func=cmd_report)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except AppError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
