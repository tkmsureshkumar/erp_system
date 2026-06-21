# Deployment Guide - GitHub

This guide will help you deploy the CTO ERP solution to GitHub.

## Prerequisites
- GitHub account (https://github.com)
- Git installed on your machine (https://git-scm.com)

## Step 1: Create a GitHub Repository

1. Go to https://github.com/new
2. Enter repository name: `cto-erp-py` (or your preferred name)
3. Add description: "Equipment Rental Operations ERP System"
4. Choose visibility: Public or Private
5. Do NOT initialize with README, .gitignore, or license (we have these locally)
6. Click "Create repository"

You'll see instructions like:
```
…or push an existing repository from the command line

git remote add origin https://github.com/YOUR_USERNAME/cto-erp-py.git
git branch -M main
git push -u origin main
```

## Step 2: Initialize Git (First Time Only)

Open PowerShell in the project root directory and run:

```powershell
cd c:\Users\tkmsu\OneDrive\Documents\erp\cto-erp-py\cto-erp-py
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

## Step 3: Stage and Commit Files

```powershell
git add .
git commit -m "Initial commit: CTO ERP application with operator, machine, and work order management"
```

## Step 4: Add Remote Repository

Replace `YOUR_USERNAME` with your GitHub username:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/cto-erp-py.git
git branch -M main
git push -u origin main
```

When prompted, enter your GitHub credentials or use a Personal Access Token.

### Using Personal Access Token (Recommended)

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (full control of private repositories)
4. Copy the token
5. When Git prompts for password, paste the token

## Step 5: Verify Upload

1. Go to your repository on GitHub
2. Verify all files are present
3. Check that the repository is properly configured

## Future Updates

After making changes locally:

```powershell
git add .
git commit -m "Describe your changes here"
git push origin main
```

## Deployment to Production

For deploying the Streamlit app to production, use:

### Option 1: Streamlit Cloud (Recommended)

1. Go to https://streamlit.io/cloud
2. Sign in with GitHub
3. Click "New app"
4. Select your repository, branch, and main file (`app.py`)
5. Deploy

Environment variables (set in Streamlit Cloud settings):
```
SUPABASE_URL=https://gsafyjbpucgbhtvvbfue.supabase.co
SUPABASE_KEY=your_service_role_key_here
```

### Option 2: Other Hosting Options

- **Heroku** (charges may apply)
- **Railway** (https://railway.app)
- **Fly.io** (https://fly.io)
- **DigitalOcean** (https://www.digitalocean.com)

## Important: Do NOT Commit Sensitive Data

The `.env` file is in `.gitignore` and will NOT be committed. Make sure:
- Never commit `.env` files
- Always use environment variables for secrets
- Review secrets before pushing to GitHub

---

**Need Help?** Check the GitHub documentation: https://docs.github.com/en/get-started
