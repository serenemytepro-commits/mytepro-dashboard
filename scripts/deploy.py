import requests, os, hashlib

NETLIFY_TOKEN   = os.environ['NETLIFY_TOKEN']
NETLIFY_SITE_ID = os.environ['NETLIFY_SITE_ID']
SCRIPT_DIR      = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT       = os.path.dirname(SCRIPT_DIR)
HTML_PATH       = os.path.join(REPO_ROOT, 'output', 'index.html')

with open(HTML_PATH, 'rb') as f:
    content = f.read()

sha  = hashlib.sha1(content).hexdigest()
auth = {'Authorization': f'Bearer {NETLIFY_TOKEN}'}

r = requests.post(
    f'https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys',
    headers={**auth, 'Content-Type':'application/json'},
    json={'files':{'/index.html': sha}}
)
r.raise_for_status()
deploy_id = r.json()['id']
print(f"Deploy created: {deploy_id}")

r2 = requests.put(
    f'https://api.netlify.com/api/v1/deploys/{deploy_id}/files/index.html',
    headers={**auth, 'Content-Type':'application/octet-stream'},
    data=content
)
r2.raise_for_status()
print("File uploaded ✓")
print("Dashboard is live and updated!")
