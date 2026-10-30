"""Legacy report generator. Kept byte-for-byte for audit reasons."""


def build_report(items):
    lines = ["INVENTORY REPORT", "================"]
    total = 0.0
    for it in items:
        lines.append("%-10s %-20s %5d %10.2f" % (it.sku, it.name, it.qty, it.price))
        total += it.qty * it.price
    avg = total / len(items)
    lines.append("----------------")
    lines.append("TOTAL %.2f  AVG/ITEM %.2f" % (total, avg))
    return "\n".join(lines)
