from invlite.cli import main


def _db(tmp_path):
    db = tmp_path / "inv.csv"
    db.write_text("sku,name,qty,price\nA1,Apple,10,0.5\nB2,Banana,3,0.25\n", encoding="utf-8")
    return str(db)


def test_table_header_and_alignment(tmp_path, capsys):
    assert main(["--db", _db(tmp_path), "list"]) == 0
    lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
    header = lines[0].split()
    assert header[:4] == ["SKU", "NAME", "QTY", "PRICE"]
    rows = [l for l in lines if l.startswith(("A1", "B2"))]
    assert len(rows) == 2
    # aligned: the NAME column starts at the same offset on every row
    assert len({l.index(n) for l, n in zip(rows, ["Apple", "Banana"])}) == 1
    assert "\x1b[" not in "\n".join(lines)


def test_color_flag(tmp_path, capsys):
    assert main(["--db", _db(tmp_path), "list", "--color"]) == 0
    out = capsys.readouterr().out
    b2 = next(l for l in out.splitlines() if l.startswith("B2"))
    a1 = next(l for l in out.splitlines() if l.startswith("A1"))
    assert "\x1b[31m" in b2 or "\x1b[91m" in b2
    assert "\x1b[31m" not in a1 and "\x1b[91m" not in a1
