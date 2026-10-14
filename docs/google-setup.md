# Google setup

Inbox Warden connects to Gmail with **Sign in with Google**, through an OAuth client in **your own** Google Cloud
project, so no third party ever holds access to your mail. It takes about five minutes, once.

## 1. Create a project and enable Gmail

1. Open [console.cloud.google.com](https://console.cloud.google.com) and create a project, e.g. "Inbox Warden".
2. **APIs & Services → Library** → search **Gmail API** → **Enable**.

## 2. Consent screen

1. **APIs & Services → OAuth consent screen** (called **Google Auth Platform** in newer consoles).
2. User type: **External** (or **Internal** if every mailbox is in your Google Workspace).
3. App name "Inbox Warden", your email as support and developer contact.
4. **Data access / Scopes** → add `https://www.googleapis.com/auth/gmail.modify`.
5. **Audience**: click **Publish app**. Apps left in "Testing" have their sign-ins expire after 7 days.
   You don't need Google's verification for your own mailboxes; at sign-in, click **Advanced → Continue**.

## 3. OAuth client

1. **Credentials → Create credentials → OAuth client ID** → application type **Web application**.
2. **Authorized redirect URIs** → add your app URL followed by `/oauth/callback`:
   - installed with the installer: `http://localhost:8080/oauth/callback` (the installer prints the exact one)
   - on a server: `https://mail.example.com/oauth/callback`
3. Copy the **Client ID** and **Client secret** into the installer (or `.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`).

## 4. Connect mailboxes

In Inbox Warden open **Mailboxes → Connect with Google** and sign in with each Gmail or Workspace account.

## What access is used

Only `gmail.modify`: read message headers and snippets, create labels, and add or remove labels (which is how
archiving and read/unread work). Inbox Warden has no code path that deletes, trashes or sends email.
Refresh tokens are encrypted at rest with your `SECRET_KEY`.
