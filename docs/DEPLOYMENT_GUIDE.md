# Production Cloud Deployment Guide: AlphaSeeker AI

**Author:** Quantitative Architecture & DevOps Engineering  
**Project:** AlphaSeeker AI Platform  
**Target:** 24/7 Cloud Production Deployment with Zero Local Machine Dependencies  

---

## 1. Cloud Deployment Options Matrix

| Method | Best For | Estimated Cost | Setup Complexity | 24/7 Daemon & Telegram |
| :--- | :--- | :---: | :---: | :---: |
| **Option 1: Cloud VPS (DigitalOcean / Hetzner / AWS EC2)** *(Recommended)* | **Full Institutional Setup**: Runs both Web Dashboard and Background Scanners 24/7 with dedicated IP. | **$4 – $6 / month** | Low – Moderate | ✅ 100% (Never sleeps) |
| **Option 2: Docker Compose** | **Local Server or Cloud Server**: One-command reproducible stack. | Same as VPS | Very Low | ✅ 100% |
| **Option 3: Streamlit Community Cloud** | **Web Dashboard Only**: Public sharing with friends/investors. | **100% Free** | 1 Click | ⚠️ Web UI only (no 24/7 background daemons) |

---

## 2. Option 1: Recommended Production Setup (Ubuntu 24.04 VPS)

### Step 1: Provision your Cloud Server
1. Create an account on **DigitalOcean**, **Hetzner**, or **AWS Lightsail**.
2. Deploy a small Linux server:
   * **OS:** Ubuntu 24.04 LTS
   * **Specs:** 1 vCPU, 2GB RAM, 25GB SSD (sufficient for scraping & running Streamlit).
   * **Cost:** ~$4 – $6 / month.

---

### Step 2: Server Security & Dependency Setup
SSH into your server:
```bash
ssh root@YOUR_SERVER_IP
```

Update system packages and install Python 3.11/git:
```bash
# Update Ubuntu packages
apt update && apt upgrade -y

# Install Python, pip, git, and Nginx
apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx ufw

# Set up UFW Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

### Step 3: Clone Codebase & Install Virtual Environment
```bash
# Clone the repository
cd /opt
git clone https://github.com/yourusername/Trading.git alphaseeker
cd alphaseeker

# Create and activate Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Step 4: Configure Production Secrets
Create your production `.env` file:
```bash
nano .env
```
Paste your Telegram Bot credentials:
```env
TELEGRAM_BOT_TOKEN="your_production_bot_token"
TELEGRAM_CHAT_ID="your_production_chat_id"
```
Press `Ctrl + O`, then `Enter`, then `Ctrl + X` to save.

---

### Step 5: Configure 24/7 Background Systemd Daemons

#### A. Web Dashboard Service (`/etc/systemd/system/alphaseeker-web.service`)
```bash
sudo nano /etc/systemd/system/alphaseeker-web.service
```
Paste the following configuration:
```ini
[Unit]
Description=AlphaSeeker AI Streamlit Web Dashboard
After=network.target

[Service]
User=root
WorkingDirectory=/opt/alphaseeker
ExecStart=/opt/alphaseeker/venv/bin/streamlit run dashboard/app.py --server.port=8501 --server.address=127.0.0.1 --server.headless=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### B. Autonomous Background Scanner Daemon (`/etc/systemd/system/alphaseeker-scanner.service`)
```bash
sudo nano /etc/systemd/system/alphaseeker-scanner.service
```
Paste the following configuration:
```ini
[Unit]
Description=AlphaSeeker AI Autonomous Market Scanner
After=network.target

[Service]
User=root
WorkingDirectory=/opt/alphaseeker
ExecStart=/opt/alphaseeker/venv/bin/python main.py --market US --timeframe swing --source live_active
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start both services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now alphaseeker-web
sudo systemctl status alphaseeker-web
```

---

### Step 6: Setup Nginx Reverse Proxy with Free SSL (HTTPS)

Configure Nginx to route domain traffic (e.g., `trading.yourdomain.com` or your Server IP) to port 8501:
```bash
sudo nano /etc/nginx/sites-available/alphaseeker
```
Paste:
```nginx
server {
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and obtain a free Let's Encrypt SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/alphaseeker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Automatically install free HTTPS SSL certificate
sudo certbot --nginx -d yourdomain.com
```

Now your dashboard is live at **`https://yourdomain.com`** protected with bank-grade SSL encryption!

---

## 3. Option 2: Docker Compose Deployment (1-Command Launch)

If you prefer containerization, you can run the entire system on any server with a single command:

```bash
# 1. Clone repository
git clone https://github.com/yourusername/Trading.git
cd Trading

# 2. Add your Telegram credentials to .env
cp .env.example .env
nano .env

# 3. Launch the complete container stack
docker compose up -d --build
```

### Useful Docker Commands:
* View live logs: `docker compose logs -f`
* Stop services: `docker compose down`
* Restart after updates: `docker compose restart`

---

## 4. Option 3: Free Streamlit Community Cloud Hosting

If you want a free web URL for the dashboard without paying for a server:
1. Push your project to a GitHub repository:
   ```bash
   git init
   git add .
   git commit -m "AlphaSeeker AI Production Release"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/Trading.git
   git push -u origin main
   ```
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and log in with GitHub.
3. Click **"New app"**:
   * Repository: `YOUR_USERNAME/Trading`
   * Branch: `main`
   * Main file path: `dashboard/app.py`
4. Under **"Advanced settings"**, add your secrets:
   ```toml
   TELEGRAM_BOT_TOKEN = "your_token"
   TELEGRAM_CHAT_ID = "your_chat_id"
   ```
5. Click **"Deploy"**. Streamlit will build your app and give you a free public link (`https://alphaseeker.streamlit.app`).

---

## 5. Ongoing Maintenance & Zero-Downtime Updates

Whenever you make improvements to strategy rules or scrapers, update your live cloud server with zero downtime:

```bash
cd /opt/alphaseeker
git pull origin main
sudo systemctl restart alphaseeker-web
```
