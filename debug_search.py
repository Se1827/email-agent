import sys
from pathlib import Path
from dotenv import load_dotenv
import imaplib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.services.accounts import load_accounts
from src.config import get_settings

cfg = get_settings()
accounts = load_accounts(cfg.data_dir)
acc = next((a for a in accounts if "elektrine" in a.imap_host), None)

if acc:
    imaplib.Debug = 4
    if acc.imap_use_ssl:
        conn = imaplib.IMAP4_SSL(acc.imap_host, acc.imap_port)
    else:
        conn = imaplib.IMAP4(acc.imap_host, acc.imap_port)
    conn.login(acc.email, acc.imap_pass)
    conn.select("INBOX")
    
    print("--- SEARCH ALL ---")
    status, data = conn.uid("SEARCH", "ALL")
    print(status, data)
    
    print("--- SEARCH UID 418000:* ---")
    status, data = conn.uid("SEARCH", "UID", "418000:*")
    print(status, data)
    
    conn.logout()
