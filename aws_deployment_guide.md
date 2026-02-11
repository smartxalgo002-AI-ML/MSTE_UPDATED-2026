# AWS Deployment Guide - News Sentiment Model
> **For First-Time AWS Users**

This guide will help you put your project on the cloud (AWS) so it runs 24/7 without needing your laptop.

Think of an **EC2 Instance** as a "Rental Computer" that lives in Amazon's data center. You will control it remotely.

---

## ✅ Prerequisites (Do this first)
1.  **Create an AWS Account**: [aws.amazon.com](https://aws.amazon.com) (Free Tier available).
2.  **Download "PuTTY"** (if on Windows) or just use your terminal.

---

## Step 1: Rent Your Computer (Launch EC2)

1.  Log in to **AWS Console**.
2.  Search for **"EC2"** in the top bar and click it.
3.  Click the orange **"Launch Instance"** button.
4.  **Name**: `News-Sentiment-Server`
5.  **OS Images**: Select **Ubuntu** (Choose "Ubuntu Server 22.04 LTS").
6.  **Instance Type**:
    - Select **t3.xlarge** (Recommended for AI models).
    - *Note: t2.micro is free but too weak for this AI model.*
7.  **Key Pair**:
    - Click **"Create new key pair"**.
    - Name it `my-aws-key`.
    - Select format **`.pem`** (for OpenSSH/Mac) or **`.ppk`** (for PuTTY).
    - **Download it and keep it safe!** (You cannot download it again).
8.  **Network Settings**:
    - Check "Allow SSH traffic".
    - Check "Allow HTTP traffic".
9.  **Storage**: Change the default "8 GiB" to **100 GiB** (AI models need space).
10. Click **Launch Instance**.

---

## Step 2: Connect to Your Server

### Option A: Using Windows PowerShell (Easier)
1.  Open PowerShell on your laptop.
2.  Go to the folder where you saved your key (e.g., `cd Downloads`).
3.  Run this command (replace with your actual key name and IP address):
    ```powershell
    ssh -i "my-aws-key.pem" ubuntu@12.34.56.78
    ```
    *(Find your IP address in the EC2 dashboard under "Public IPv4 address").*

4.  Type `yes` if asked. You are now inside the server!

---

## Step 3: Install Software

Copy and paste these commands into your server terminal (one block at a time):

**1. Update the system:**
```bash
sudo apt update && sudo apt upgrade -y
```

**2. Install Python and Git:**
```bash
sudo apt install python3 python3-pip python3-venv git -y
```

**3. Install Chrome (for news scraping):**
```bash
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install ./google-chrome-stable_current_amd64.deb -y
```

---

## Step 4: Download Your Project

Since you pushed your code to GitHub, we can just download it!

```bash
# Clone your repository (You will need your username & password/token)
git clone https://github.com/smartxalgo002-AI-ML/MSTE_Testing_2026.git

# Go into the folder
cd MSTE_Testing_2026/News_Sentiment_Model_Step1
```

---

## Step 5: Setup Python

We create a "virtual environment" to keep things clean.

```bash
# Create environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install all libraries (This takes 5-10 mins)
pip install -r requirements.txt

# Download AI helper data
python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

---

## Step 6: Add Your Trading Token

Your `dhan_token.json` is private, so it's not on GitHub. You must create it manually.

```bash
cd "correct_ohlcv_tick_data"
nano dhan_token.json
```

**Paste your token details like this:**
```json
{
  "access_token": "YOUR_LONG_TOKEN_HERE",
  "client_id": "1108324336",
  "expires_at": 1770267170,
  "renewed_at": 1738644770
}
```
*(Press `Ctrl+O`, `Enter` to Save, then `Ctrl+X` to Exit)*.

---

## Step 7: Run 24/7 (Background Mode)

We use a tool called `tmux` so the program keeps running even if you close your laptop.

```bash
# 1. Install tmux
sudo apt install tmux -y

# 2. Start a new session named 'pipeline'
tmux new -s pipeline

# 3. Make scripts executable
cd ~/MSTE_Testing_2026/News_Sentiment_Model_Step1
chmod +x start.sh run_dashboard.sh

# 4. Start the system!
./start.sh
```

**🎉 Success! The system is now running.**

- **To leave it running:** Press `Ctrl+B`, release, then press `D` (Detach).
- **To see it again later:** Type `tmux attach -t pipeline`.

---

## Step 8: Use Systemd (Professional Way - Highly Recommended)

Instead of `tmux`, you can set the system to start automatically when the server reboots and restart automatically if it crashes.

```bash
# 1. Copy service files to Systemd
sudo cp news_pipeline.service /etc/systemd/system/
sudo cp ohlcv_collector.service /etc/systemd/system/
sudo cp dashboard.service /etc/systemd/system/

# 2. Refresh systemd
sudo systemctl daemon-reload

# 3. Enable them to start on boot
sudo systemctl enable news_pipeline ohlcv_collector dashboard

# 4. Start them
sudo systemctl start news_pipeline ohlcv_collector dashboard

# 5. Check status
sudo systemctl status news_pipeline
```

*Note: The service files assume the project is in `/home/ubuntu/MSTE_Testing_2026/News_Sentiment_Model_Step1`. If you cloned it into a different folder, you must edit the `WorkingDirectory` and `ExecStart` lines in the `.service` files using `nano`.*

---

## Step 9: View Dashboard (Optional)

1.  Start a second session:
    ```bash
    tmux new -s dashboard
    ./run_dashboard.sh
    ```
2.  Detach (`Ctrl+B`, `D`).
3.  On AWS Console -> Security Groups -> Edit Inbound Rules -> Add Rule -> **Custom TCP**, Port **8501**, Source **Anywhere**.
4.  Open browser: `http://YOUR-EC2-IP:8501`

---

## 🆘 Troubleshooting

- **"Permission denied" on SSH**:
  - Run `chmod 400 my-aws-key.pem` on your Mac/Linux (or properties -> security on Windows) to secure the key.

- **System runs out of memory**:
  - You probably chose `t2.micro`. You need `t3.xlarge` because AI models are heavy.

- **Dhan Token Invalid**:
  - Double check you pasted the correct token in Step 6.
