import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = 4  # Four parallel processes to handle 4 PDFs at once
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120  # Seconds before a stuck worker is killed