import os, re, logging
from datetime import datetime
import pdfplumber
import pandas as pd
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title="KC FinanceHub Python Service")
ALLOWED_MIME = "application/pdf"
MAX_SIZE = 10 * 1024 * 1024  # 10 MB

def parse_bank_pdf(file_path: str) -> dict:
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    if not text.strip():
        raise ValueError("No text extracted from PDF")
    lines = text.split("\n")
    data = []
    for line in lines:
        date_match = re.search(r"(\d{2}[/-]\d{2}[/-]\d{2,4})", line)
        if not date_match:
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 3:
            continue
        date = parts[0]
        particulars = " ".join(parts[1:-1])
        amount_str = parts[-1].replace(",", "")
        try:
            amount = float(re.sub(r"[^\d.-]", "", amount_str))
        except ValueError:
            continue
        data.append({"date": date, "description": particulars, "amount": amount})
    if not data:
        raise ValueError("No transactions parsed from PDF")
    df = pd.DataFrame(data)
    credits = df[df["amount"] > 0]["amount"].sum()
    debits = df[df["amount"] < 0]["amount"].sum()
    high_value_count = int((df["amount"].abs() > 50000).sum())
    categories = df["description"].value_counts().head(10).to_dict()
    return {
        "total_credits": round(credits, 2),
        "total_debits": round(abs(debits), 2),
        "net_flow": round(credits - abs(debits), 2),
        "transaction_count": len(df),
        "high_value_count": high_value_count,
        "top_categories": categories,
    }

@app.post("/parse-bank-pdf")
async def parse_bank_pdf_endpoint(file: UploadFile = File(...)):
    if file.content_type != ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="Invalid file type. Only PDF allowed.")
    file_content = await file.read()
    if len(file_content) > MAX_SIZE:
        raise HTTPException(status_code=422, detail="File too large. Max 10MB.")
    temp_path = f"/tmp/{datetime.now().timestamp()}_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(file_content)
    try:
        summary = parse_bank_pdf(temp_path)
        os.remove(temp_path)
        return JSONResponse(content=summary, status_code=200)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        logger.error(f"Parse error: {str(e)}")
        raise HTTPException(status_code=422, detail=f"Invalid PDF: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
