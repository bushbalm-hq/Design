#!/usr/bin/env python3
"""Refresh the Monday snapshot embedded in index.html.

Pulls the "2026 Yearly Calendar - Brand" board, replaces SNAPSHOT_DATA_JSON,
keeps manual `local-*` items, and bumps the "Updated" chip only if data changed.

Usage:
  MONDAY_API_TOKEN=... python3 scripts/refresh_snapshot.py
  python3 scripts/refresh_snapshot.py --from-file response.json   # offline/testing
"""
import argparse, datetime, json, os, re, sys, urllib.request

BOARD_ID = 8798824140
# Order matters: brand, launch, campaign, photoshoot, liveshopping, event, sale, nationalday
GROUP_IDS = ["group_mkw2dr49", "new_group40901", "new_group35240", "new_group_mkkzvjmv",
             "group_mkxerf23", "group_mkygtnt3", "new_group20103", "group_mkws3yx4"]
QUERY = """query { boards(ids: [%d]) { groups(ids: [%s]) { id title items_page(limit: 200) {
  cursor items { id name column_values(ids: ["timeline"]) { id text } } } } } }""" % (
    BOARD_ID, ",".join('"%s"' % g for g in GROUP_IDS))

HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")


def fetch_live(token):
    req = urllib.request.Request(
        "https://api.monday.com/v2",
        data=json.dumps({"query": QUERY}).encode(),
        headers={"Authorization": token, "Content-Type": "application/json",
                 "API-Version": "2024-10"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = json.load(r)
    if body.get("errors") or "data" not in body:
        sys.exit("Monday API error: %s" % json.dumps(body.get("errors") or body)[:500])
    return body["data"]


def merge(old, live):
    groups = {g["id"]: g for g in live["boards"][0]["groups"]}
    missing = [g for g in GROUP_IDS if g not in groups]
    if missing:
        sys.exit("Groups missing from Monday response (renamed/deleted?): %s" % missing)
    old_groups = {g["id"]: g for g in old["boards"][0]["groups"]}
    out = []
    for gid in GROUP_IDS:
        g = groups[gid]
        if g["items_page"].get("cursor"):
            sys.exit("Group %s has more than 200 items; add pagination." % gid)
        local = [i for i in old_groups.get(gid, {}).get("items_page", {}).get("items", [])
                 if str(i["id"]).startswith("local-")]
        g["items_page"]["items"] = g["items_page"]["items"] + local
        out.append(g)
    return {"boards": [{"groups": out}]}


def summarize(old, new):
    def flat(d):
        return {i["id"]: (i["name"], (i["column_values"] or [{}])[0].get("text"), g["id"])
                for g in d["boards"][0]["groups"] for i in g["items_page"]["items"]}
    a, b = flat(old), flat(new)
    for k in b.keys() - a.keys(): print("  + %s | %s" % (b[k][0], b[k][1]))
    for k in a.keys() - b.keys(): print("  - %s | %s" % (a[k][0], a[k][1]))
    for k in a.keys() & b.keys():
        if a[k] != b[k]: print("  ~ %s | %s  ->  %s | %s" % (a[k][0], a[k][1], b[k][0], b[k][1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file")
    args = ap.parse_args()
    if args.from_file:
        live = json.load(open(args.from_file))
        live = live.get("data", live)
    else:
        token = os.environ.get("MONDAY_API_TOKEN")
        if not token:
            sys.exit("Set MONDAY_API_TOKEN")
        live = fetch_live(token)

    content = open(HTML, encoding="utf-8").read()
    m = re.search(r'const SNAPSHOT_DATA_JSON = (".*?");\n', content)
    if not m:
        sys.exit("SNAPSHOT_DATA_JSON not found in index.html")
    old = json.loads(json.loads(m.group(1)))
    new = merge(old, live)

    if new == old:
        print("No changes.")
        return
    summarize(old, new)
    js = json.dumps(json.dumps(new, ensure_ascii=False, separators=(",", ":")), ensure_ascii=False)
    content = content[:m.start(1)] + js + content[m.end(1):]
    today = datetime.date.today()
    stamp = "Updated %s %d, %d" % (today.strftime("%b"), today.day, today.year)
    content, n = re.subn(r"Updated [A-Z][a-z]{2} \d{1,2}, \d{4}", stamp, content, count=1)
    if n != 1:
        sys.exit("'Updated …' chip not found")
    open(HTML, "w", encoding="utf-8").write(content)
    print("Updated index.html (%s)." % stamp)


if __name__ == "__main__":
    main()
