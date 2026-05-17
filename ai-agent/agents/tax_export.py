import argparse
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from agents.invoices import load_tax_config
from core.tax_export import export_tax_year


def main():
    parser = argparse.ArgumentParser(description="Jahresuebersicht fuer die Einkommensteuer aus Rechnungen erzeugen.")
    parser.add_argument("--year", type=int, required=True, help="Steuerjahr, z.B. 2025.")
    args = parser.parse_args()

    result = export_tax_year(load_tax_config(), args.year)
    print(result)


if __name__ == "__main__":
    main()
