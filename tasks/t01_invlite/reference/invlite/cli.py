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


RED = "\x1b[31m"
RESET = "\x1b[0m"
LOW_STOCK = 5


def cmd_list(args):
    store = _load(args.db)
    rows = [(i.sku, i.name, str(i.qty), f"{i.price:.2f}") for i in store.list_items()]
    header = ("SKU", "NAME", "QTY", "PRICE")
    widths = [max(len(r[c]) for r in [header] + rows) for c in range(4)]

    def fmt(row, qty_color=False):
        cells = [row[0].ljust(widths[0]), row[1].ljust(widths[1]), row[2].rjust(widths[2]), row[3].rjust(widths[3])]
        if qty_color:
            cells[2] = f"{RED}{cells[2]}{RESET}"
        return "  ".join(cells)

    echo(fmt(header))
    echo("  ".join("-" * w for w in widths))
    for row in rows:
        echo(fmt(row, qty_color=getattr(args, "color", False) and int(row[2]) < LOW_STOCK))


def cmd_value(args):
    store = _load(args.db)
    echo(f"{store.total_value():.2f}")


def cmd_report(args):
    from legacy.old_report import build_report

    store = _load(args.db)
    items = store.list_items()
    if not items:
        # legacy/ must stay byte-for-byte, so the empty case is handled here.
        echo("\n".join(["INVENTORY REPORT", "================", "----------------", "TOTAL 0.00  AVG/ITEM 0.00"]))
        return
    echo(build_report(items))


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

    p_list = sub.add_parser("list")
    p_list.add_argument("--color", action="store_true", help="highlight low stock in red")
    p_list.set_defaults(func=cmd_list)
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
