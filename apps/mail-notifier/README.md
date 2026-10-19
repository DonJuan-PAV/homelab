# mail-notifier

Counts **important** new emails in Outlook and Gmail and shows the numbers on a [Homepage](https://gethomepage.dev) dashboard. Ads, newsletters, replies, auto-replies and no-reply senders are not counted.

```
Outlook (Graph API) ──┐
                      ├──► filter ──► count ──► /stats ──► Homepage tile:  Outlook 2 · Gmail 1 · Today 3
Gmail (IMAP)  ────────┘
```

- **Read-only**: nothing is ever marked as read, moved or deleted.
- **Only numbers** leave the server: `/stats` never contains subjects or senders.
- **Counted once**: a small SQLite database remembers what it has seen, even after a restart.
- Gmail: only the **Primary** tab is checked, so Promotions/Social/Updates never count.
- If one mailbox fails (Gmail down, login expired), the other keeps working.

## Setup

### 1. Outlook (optional)

Reuse the Azure app from mail2jira: copy its **Application (client) ID** into `OUTLOOK_CLIENT_ID`. The app only needs the **Mail.Read** permission and **Allow public client flows = Yes**.

### 2. Gmail (optional)

1. Turn on **2-Step Verification** for the Google account (required for app passwords).
2. Go to **myaccount.google.com/apppasswords**, create an app password named `mail-notifier`.
3. Copy the 16-character password into `GMAIL_APP_PASSWORD` (spaces don't matter).

An app password only works for mail access, and you can revoke it at any time from the same page without changing your real password.

### 3. Configure and run

```bash
cp .env.example .env     # fill in OUTLOOK_CLIENT_ID and/or the Gmail settings
mkdir -p data
docker compose up -d --build
docker logs -f mail-notifier   # first run: sign in to Outlook with the link + code shown
```

Check the numbers: `curl http://localhost:8090/stats`

```json
{"today": 3, "total": 3, "outlook_today": 1, "outlook_total": 1, "gmail_today": 2, "gmail_total": 2, "last_check": "2026-10-18T22:16:40-04:00"}
```

### 4. Homepage widget

Add to Homepage's `services.yaml` (replace `SERVER-IP`):

```yaml
- Mail:
    - Important mail:
        icon: mdi-email-alert
        description: New important emails today
        widget:
          type: customapi
          url: http://SERVER-IP:8090/stats
          refreshInterval: 60000
          mappings:
            - field: outlook_today
              label: Outlook
              format: number
            - field: gmail_today
              label: Gmail
              format: number
            - field: today
              label: Total today
              format: number
```

The counters reset at midnight (server time). `*_total` fields count everything since the first run.

## Tuning

- **Filter rules** (what counts as noise): `src/filters.py`
- **Gmail search**: set `GMAIL_SEARCH` with Gmail's search syntax. Default: `in:inbox category:primary is:unread newer_than:2d`
- **Outlook Focused inbox only**: `OUTLOOK_FOCUSED_ONLY=true`
- **Start counting from zero**: stop the container and delete `data/notifier.db`.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```
