from invlite.cli import main


def test_report_empty(tmp_path, capsys):
    db = tmp_path / "inv.csv"
    db.write_text("sku,name,qty,price\n", encoding="utf-8")
    assert main(["--db", str(db), "report"]) == 0
    out = capsys.readouterr().out
    assert "INVENTORY REPORT" in out
    assert "TOTAL 0.00" in out


def test_report_non_empty_unchanged(tmp_path, capsys):
    db = tmp_path / "inv.csv"
    db.write_text("sku,name,qty,price\nA1,Apple,2,1.5\n", encoding="utf-8")
    assert main(["--db", str(db), "report"]) == 0
    assert "TOTAL 3.00  AVG/ITEM 3.00" in capsys.readouterr().out
