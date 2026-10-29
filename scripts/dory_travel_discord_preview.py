"""Static preview of the `/dory flights` and `/dory hotels` Discord messages (offline, no Discord).

Builds the REAL payloads of `dory.travel_search_bot` for each step of the journey (flight results,
after a filter, page 2, fare review, hotel results, rooms, stay review, the expired-search reply,
and the Thai results page) and renders them as one HTML page that imitates Discord's dark message
UI closely enough to judge the layout. Optionally screenshots it with Playwright.

    uv run python scripts/dory_travel_discord_preview.py --out /tmp/dory-discord [--png]
"""

from __future__ import annotations

import argparse
import base64
import html
import re
from datetime import date, timedelta
from pathlib import Path

from dory import travel_search as ts
from dory import travel_search_bot as tb
from dory import trips
from dory.i18n import t

TODAY = date(2026, 10, 29)
AVATAR = Path(__file__).resolve().parents[1] / "src/meeting_scribe/static/dory/favicon.png"
EYE = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 5C5.6 5 2 '
    '12 2 12s3.6 7 10 7 10-7 10-7-3.6-7-10-7Zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8Z"/></svg>'
)
CSS = """
body{margin:0;background:#313338;color:#dbdee1;font:16px/1.375 "gg sans","Noto Sans","Helvetica Neue",
 Helvetica,Arial,"Thonburi",sans-serif}
main{max-width:860px;padding:24px 16px 48px}
h1{font-size:20px;color:#f2f3f5;margin:0 0 4px}
.lead{color:#b5bac1;font-size:14px;margin:0 0 24px}
.step{padding:16px 0 20px;border-top:1px solid #3f4147}
.label{font:600 12px/1 sans-serif;letter-spacing:.04em;text-transform:uppercase;color:#949ba4;
 margin:0 0 12px 72px}
.reply{display:flex;align-items:center;gap:6px;margin-left:72px;font-size:14px;color:#b5bac1}
.reply .who{color:#c9cdfb;font-weight:500}.reply .cmd{color:#00a8fc}
.msg{display:flex;gap:16px;padding:2px 16px 2px 16px}
.av{width:40px;height:40px;border-radius:50%;flex:none;background:#1e1f22;overflow:hidden}
.av img{width:40px;height:40px}
.head{display:flex;align-items:center;gap:6px}
.name{color:#f2f3f5;font-weight:500}
.app{background:#5865f2;color:#fff;font:600 10px/16px sans-serif;padding:0 4px;border-radius:3px}
.time{color:#949ba4;font-size:12px}
.body{min-width:0;flex:1;max-width:640px}
.td{white-space:normal;word-wrap:break-word;margin:2px 0}
.td h1{font-size:24px;margin:8px 0 2px;color:#f2f3f5}
.td h2{font-size:20px;margin:6px 0 2px;color:#f2f3f5}
.td h3{font-size:16px;margin:4px 0 2px;color:#f2f3f5}
.td .sub{font-size:13px;color:#949ba4;line-height:1.3}
.td code{background:#1e1f22;border-radius:4px;padding:1px 4px;font:13px/1.4 Menlo,Consolas,monospace;
 color:#dbdee1}
.td strong{color:#f2f3f5}
.ctr{background:#2b2d31;border:1px solid #1e1f22;border-radius:8px;padding:16px;margin:8px 0;
 position:relative;overflow:hidden}
.ctr::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}
.sep{border-top:1px solid #3f4147;margin:10px 0}
.row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.btn{height:32px;padding:0 16px;border-radius:8px;border:0;color:#fff;font:500 14px/32px sans-serif;
 white-space:nowrap}
.b1{background:#5865f2}.b2{background:#4e5058}.b4{background:#da373c}.b3{background:#248046}
.btn[disabled]{opacity:.5}
.sel{flex:1;min-width:300px;max-width:560px;height:40px;background:#1e1f22;border-radius:8px;
 display:flex;align-items:center;justify-content:space-between;padding:0 12px;color:#dbdee1;
 font-size:14px;border:1px solid #1e1f22}
.sel .ph{color:#949ba4}.sel .chev{color:#b5bac1;margin-left:8px}
.eph{display:flex;align-items:center;gap:6px;color:#949ba4;font-size:12px;margin-top:6px}
.eph a{color:#00a8fc}
.plain{margin:2px 0}
"""


def md(text: str) -> str:
    """The Discord markdown the payloads use: headings, subtext, bold, inline code."""
    out = []
    for line in text.split("\n"):
        e = html.escape(line)
        e = re.sub(r"`([^`]+)`", r"<code>\1</code>", e)
        e = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e)
        for mark, tag in (("### ", "h3"), ("## ", "h2"), ("# ", "h1")):
            if e.startswith(mark):
                out.append(f"<{tag}>{e[len(mark) :]}</{tag}>")
                break
        else:
            out.append(
                f'<div class="sub">{e[3:]}</div>'
                if e.startswith("-# ")
                else (f"<div>{e}</div>" if e else "<div>&nbsp;</div>")
            )
    return "".join(out)


def component(c: dict) -> str:
    kind = c["type"]
    if kind == 10:
        return f'<div class="td">{md(c["content"])}</div>'
    if kind == 14:
        return '<div class="sep"></div>'
    if kind == 17:
        inner = "".join(component(x) for x in c["components"])
        return f'<div class="ctr" style="--accent:#{c["accent_color"]:06x}">{inner}</div>'
    if kind == 1:
        return '<div class="row">' + "".join(component(x) for x in c["components"]) + "</div>"
    if kind == 2:
        off = " disabled" if c.get("disabled") else ""
        return f'<button class="btn b{c["style"]}"{off}>{html.escape(c["label"])}</button>'
    if kind == 3:
        chosen = [o["label"] for o in c["options"] if o.get("default")]
        shown = (
            html.escape(", ".join(chosen))
            if chosen
            else f'<span class="ph">{html.escape(c.get("placeholder") or "")}</span>'
        )
        return f'<div class="sel"><span>{shown}</span><span class="chev">&#9662;</span></div>'
    return f"<pre>{html.escape(str(c))}</pre>"


EPH = f'<div class="eph">{EYE}<span>Only you can see this · <a>Dismiss message</a></span></div>'


def message(label: str, command: str, body: str, avatar: str) -> str:
    chat = command.startswith("@Dory")  # a chat message: cards in the channel, not ephemeral
    said = "" if chat else " used "
    return f"""<section class="step"><p class="label">{html.escape(label)}</p>
<div class="reply"><span class="who">@you</span>{said or ": "}<span class="cmd">{html.escape(command)}</span></div>
<div class="msg"><div class="av"><img src="{avatar}" alt=""></div><div class="body">
<div class="head"><span class="name">Dory</span><span class="app">APP</span>
<span class="time">Today at 14:02</span></div>{body}
{"" if chat else EPH}
</div></div></section>"""


def steps() -> list[tuple[str, str, object]]:
    """(label, command, LayoutView or plain text) for each step of the journey."""
    sessions = ts.Sessions()
    lang = "en"
    fq, _ = tb.flight_query({"origin": "BKK", "destination": "SIN", "adults": 2}, TODAY, lang)
    s = sessions.start("discord:1", "flights", fq)
    out = [
        (
            "1 · Flight results, page 1",
            "/dory flights from:BKK to:SIN travellers:2",
            tb.results_view(tb.run_search(s, TODAY), s, lang),
        )
    ]
    out.append(
        (
            "2 · After the filter Non-stop + sort Cheapest",
            "/dory flights",
            (
                tb.travel_click(s, "ff", "", ["nonstop"], TODAY, lang),
                tb.travel_click(s, "fs", "", ["cheapest"], TODAY, lang),
            )[1],
        )
    )
    out.append(
        (
            "3 · Next page (page 2)",
            "/dory flights",
            tb.travel_click(s, "pg", str(tb.PAGE), [], TODAY, lang),
        )
    )
    tb.travel_click(s, "cl", "", [], TODAY, lang)
    one_stop = next(o["id"] for o in ts.flight_offers(fq) if o["stops"])
    out.append(
        (
            "4 · Select flight: the fare review",
            "/dory flights",
            tb.travel_click(s, "fl", one_stop, [], TODAY, lang),
        )
    )
    hq, _ = tb.hotel_query({"city": "SIN", "nights": 3, "rooms": 1, "guests": 2}, TODAY, lang)
    h = sessions.start("discord:1", "hotels", hq)
    out.append(
        (
            "5 · Hotel results",
            "/dory hotels city:SIN",
            tb.results_view(tb.run_search(h, TODAY), h, lang),
        )
    )
    out.append(
        (
            "6 · View rooms",
            "/dory hotels",
            tb.travel_click(h, "ho", "harbourlight", [], TODAY, lang),
        )
    )
    out.append(
        (
            "7 · Choose a room: the stay review",
            "/dory hotels",
            tb.travel_click(h, "rm", "harbourlight", ["deluxe-king"], TODAY, lang),
        )
    )
    out.append(
        (
            "8 · A click on an expired search (or someone else's)",
            "/dory flights",
            t("discord.search.expired", lang),
        )
    )
    th = sessions.start("discord:1", "flights", fq)
    out.append(
        (
            "9 · Thai: flight results, page 1",
            "/dory flights from:BKK to:SIN travellers:2",
            tb.results_view(tb.run_search(th, TODAY), th, "th"),
        )
    )
    ctx = ts.CardCtx(owner="discord:1", today=TODAY, trips=ts.Trips())
    search_flights, _ = ts.card_tools(ctx)
    search_flights(origin="Bangkok", destination="Singapore", depart_date=fq.depart.isoformat(),
                   travellers=2, stops="nonstop")  # fmt: skip
    chat = tb.card_session(sessions, "discord:1", ts.tool_cards([search_flights])[0])
    out.append(
        (
            "10 · Cards posted under a chat answer (the brain called search_flights)",
            "@Dory non-stop flights Bangkok to Singapore next Tuesday for 2 of us",
            tb.results_view(tb.run_search(chat, TODAY), chat, lang),
        )
    )
    # Book in sandbox from the stay review, with the flight of step 4, a way back and the room
    friday = fq.depart + timedelta(days=3)
    back = ts.search_flights(
        ts.FlightQuery(origin="SIN", destination="BKK", depart=friday, adults=2)
    )
    picked = {"flight": s.extra["ref"], "return": back["results"][0]["booking_ref"],
              "room": h.extra["ref"]}  # fmt: skip
    items = tb.booking_items(picked, TODAY)
    out.append(
        (
            "11 · Book in sandbox: the quote (a new message only the person sees)",
            "/dory hotels",
            tb.quote_view(h, items, list(items), lang),
        )
    )
    total = sum(tb._item(k, v, lang)[1] for k, v in items.items())
    done = {"status": "booked", "trip_id": "T-5f3a9c21", "filed_receipts": [41, 42],
            "references": {"flight": trips.pnr("preview"), "hotel": trips.pnr("preview", 8)},
            "totals": [{"amount": total, "currency": "THB"}], "checkin_reminder": "R-0007"}  # fmt: skip
    out.append(
        (
            "12 · Confirm booking: booked in the sandbox (sample references)",
            "/dory hotels",
            tb.booked_view(done, items, h, lang),
        )
    )
    return out


def render() -> str:
    avatar = "data:image/png;base64," + base64.b64encode(AVATAR.read_bytes()).decode()
    parts = []
    for label, command, payload in steps():
        if isinstance(payload, str):
            body = f'<div class="plain">{html.escape(payload)}</div>'
        else:
            stats = f"{payload.total_children_count}/40 components, {payload.content_length()}/4000 chars"
            label = f"{label} — {stats}"
            body = "".join(component(c) for c in payload.to_components())
        parts.append(message(label, command, body, avatar))
    return (
        f"<!doctype html><meta charset='utf-8'><title>Dory Discord preview</title>"
        f"<style>{CSS}</style><main><h1>Dory · /dory flights and /dory hotels</h1>"
        f"<p class='lead'>Rendered from the real payloads of dory.travel_search_bot "
        f"(Components V2), sample data of {TODAY:%d %b %Y}. An imitation of Discord's dark "
        f"theme, not a screenshot of Discord.</p>{''.join(parts)}</main>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/dory-discord-preview")
    ap.add_argument("--png", action="store_true", help="screenshot with Playwright (chromium)")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    page = out / "discord-preview.html"
    page.write_text(render(), encoding="utf-8")
    print(page)
    if args.png:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            tab = browser.new_page(viewport={"width": 900, "height": 900}, device_scale_factor=1)
            tab.goto(page.as_uri())
            tab.screenshot(path=str(out / "discord-preview.png"), full_page=True)
            for i, step in enumerate(tab.query_selector_all("section.step"), 1):
                step.screenshot(path=str(out / f"discord-preview-{i}.png"))
            browser.close()
        print(out / "discord-preview.png")


if __name__ == "__main__":
    main()
