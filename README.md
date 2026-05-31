# KC FinanceHub Python Service

Deploy on Railway:
1. Push this folder to a GitHub repository.
2. In Railway (railway.app), create a new project → "Deploy from GitHub repo".
3. Select the repository.
4. Set the root directory to `/python-service`.
5. Set the Start Command: `gunicorn -c gunicorn_conf.py app:app`
6. Railway auto-detects `requirements.txt` and installs the dependencies.
7. After deployment, note the public URL (e.g., `https://kc-python-service.up.railway.app`).

Update the Edge Function's `PYTHON_API_URL` environment variable with this URL.