from pypdf import PdfReader

reader = PdfReader(r"c:\Users\agaurav7\Desktop\Data Modeling\OH Data Hackathon 2026.pdf")
for i, page in enumerate(reader.pages):
    print(f"--- PAGE {i+1} ---")
    print(page.extract_text())
