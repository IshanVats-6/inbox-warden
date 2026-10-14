# Google setup

Inbox Warden talks to Gmail through your own Google Cloud project, so no third party ever holds access to your mail.
Pick one (or both) of the two ways to connect mailboxes.

| | Sign in with Google (OAuth) | Domain-wide delegation |
|---|---|---|
| Works for | Any Gmail or Google Workspace account | Google Workspace, when you are the admin |
| Adding a mailbox | The owner clicks **Connect with Google** | Type the address, nobody signs in |
| Best for | A handful of mailboxes | Many mailboxes in one company |

## 1. Create the project and enable Gmail

1. Open [console.cloud.google.com](https://console.cloud.google.com) and create a project (e.g. "Inbox Warden").
2. **APIs & Services → Library** → enable the **Gmail API**.

## 2. OAuth client (Sign in with Google)

1. **APIs & Services → OAuth consent screen**: user type **External** (or Internal on Workspace), add the scope
   `https://www.googleapis.com/auth/gmail.modify`.
2. Click **Publish app**. While an app is in "Testing", Google expires sign-ins after 7 days.
   An unverified app works for your own accounts; users see a warning and click **Advanced → Continue**.
3. **Credentials → Create credentials → OAuth client ID** → type **Web application**.
4. Authorized redirect URI: `<PUBLIC_URL>/oauth/callback`, e.g. `https://mail.example.com/oauth/callback`.
5. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

## 3. Domain-wide delegation (optional, Workspace admins)

1. **IAM & Admin → Service accounts → Create** → open it → **Keys → Add key → JSON**.
   If key creation is blocked, an organization policy (`iam.disableServiceAccountKeyCreation`) is on;
   an Organization Policy Administrator can override it for this project only.
2. Copy the service account's numeric **Client ID**.
3. In [admin.google.com](https://admin.google.com) → **Security → Access and data control → API controls →
   Domain-wide delegation → Add new**: paste the Client ID, scope `https://www.googleapis.com/auth/gmail.modify`.
   Repeat in every Workspace organization whose mailboxes you want to add.
4. Mount the JSON key into the container and set `GOOGLE_SERVICE_ACCOUNT_FILE` (e.g. `/data/service-account.json`).
5. Add mailboxes by address on the **Mailboxes** page.

## What access is used

Only the `gmail.modify` scope: read message metadata, create labels, add/remove labels (which is how archiving and
read/unread work). Inbox Warden has no code path that deletes, trashes or sends email.
