"""Check for duplicate emails in the API response."""
import httpx

r = httpx.get("http://localhost:8000/api/emails", timeout=60.0)
data = r.json()

ids = [e["id"] for e in data]
subjects = [e["subject"] for e in data]

print(f"Total: {len(data)} emails")
print(f"Unique IDs: {len(set(ids))}")
print(f"Unique subjects: {len(set(subjects))}")

dupes = [s for s in set(subjects) if subjects.count(s) > 1]
if dupes:
    print(f"DUPLICATE subjects: {dupes}")
else:
    print("No duplicate subjects. PASS!")

# Show sample IDs to verify format
for e in data[:5]:
    cls_str = e.get("classification", {})
    priority = cls_str.get("priority", "?") if cls_str else "unclassified"
    print(f"  ID: {e['id'][:30]}... | {priority:12s} | {e['subject'][:40]}")
