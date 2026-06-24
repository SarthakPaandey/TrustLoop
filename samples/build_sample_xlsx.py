"""Helper to materialize samples/sample_questionnaire.xlsx from the .txt sibling."""

from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent


def main() -> None:
    src = HERE / "sample_questionnaire.txt"
    questions = [line.strip() for line in src.read_text().splitlines() if line.strip()]

    wb = Workbook()
    ws = wb.active
    ws.title = "Security Questionnaire"
    ws.append(["#", "Question", "Response"])
    for i, q in enumerate(questions, start=1):
        ws.append([i, q, ""])
    for col, width in {1: 6, 2: 60, 3: 50}.items():
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

    out = HERE / "sample_questionnaire.xlsx"
    wb.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
