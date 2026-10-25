"""Build the Dory architecture diagram (draw.io XML) with official Google Cloud icons embedded."""

import base64
import html
import sys
from pathlib import Path

GCP, SI, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
FONT = "fontFamily=Helvetica;"


def uri(svg_bytes):
    return "data:image/svg+xml," + base64.b64encode(svg_bytes).decode()


def svg_file(p):
    return open(p, "rb").read()


ICON = {
    k: uri(svg_file(f"{GCP}/{k}/{k}.svg"))
    for k in [
        "cloud_run",
        "pubsub",
        "firestore",
        "cloud_storage",
        "secret_manager",
        "vertexai",
        "text-to-speech",
    ]
}
d = svg_file(f"{SI}/discord.svg").replace(b"<svg ", b'<svg fill="#5865F2" ', 1)
ICON["discord"] = uri(d)
ICON["line"] = uri(svg_file(f"{SI}/line.svg").replace(b"<svg ", b'<svg fill="#00C300" ', 1))
WEB = "M16.36,14C16.44,13.34 16.5,12.68 16.5,12C16.5,11.32 16.44,10.66 16.36,10H19.74C19.9,10.64 20,11.31 20,12C20,12.69 19.9,13.36 19.74,14M14.59,19.56C15.19,18.45 15.65,17.25 15.97,16H18.92C17.96,17.65 16.43,18.93 14.59,19.56M14.34,14H9.66C9.56,13.34 9.5,12.68 9.5,12C9.5,11.32 9.56,10.65 9.66,10H14.34C14.43,10.65 14.5,11.32 14.5,12C14.5,12.68 14.43,13.34 14.34,14M12,19.96C11.17,18.76 10.5,17.43 10.09,16H13.91C13.5,17.43 12.83,18.76 12,19.96M8,8H5.08C6.03,6.34 7.57,5.06 9.4,4.44C8.8,5.55 8.35,6.75 8,8M5.08,16H8C8.35,17.25 8.8,18.45 9.4,19.56C7.57,18.93 6.03,17.65 5.08,16M4.26,14C4.1,13.36 4,12.69 4,12C4,11.31 4.1,10.64 4.26,10H7.64C7.56,10.66 7.5,11.32 7.5,12C7.5,12.68 7.56,13.34 7.64,14M12,4.03C12.83,5.23 13.5,6.57 13.91,8H10.09C10.5,6.57 11.17,5.23 12,4.03M18.92,8H15.97C15.65,6.75 15.19,5.55 14.59,4.44C16.43,5.07 17.96,6.34 18.92,8M12,2C6.47,2 2,6.5 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"
ICON["web"] = uri(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="#5F6368" d="{WEB}"/></svg>'.encode()
)

cells, n = [], [0]


def nid():
    n[0] += 1
    return f"c{n[0]}"


def vertex(value, style, x, y, w, h, cid=None):
    cid = cid or nid()
    cells.append(
        f'<mxCell id="{cid}" value="{html.escape(value, quote=True)}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )
    return cid


def edge(src, dst, style, value=""):
    cells.append(
        f'<mxCell id="{nid()}" value="{html.escape(value, quote=True)}" style="{style}" edge="1" parent="1" source="{src}" target="{dst}">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def label(title, sub, sub_color="#5F6368", size=14):
    return f'<b>{title}</b><br><font style="font-size:{size}px" color="{sub_color}">{sub}</font>'


CARD = (
    "rounded=1;arcSize=8;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#DADCE0;strokeWidth=1.5;align=left;verticalAlign=middle;spacingRight=8;fontSize=17;fontColor=#202124;"
    + FONT
)


def card(title, sub, x, y, w, h=104, icon=None, extra=""):
    c = vertex(
        label(title, sub),
        CARD + ("spacingLeft=66;" if icon else "spacingLeft=16;") + extra,
        x,
        y,
        w,
        h,
    )
    if icon:
        vertex(
            "",
            f"shape=image;aspect=fixed;imageAspect=0;image={ICON[icon]};",
            x + 14,
            y + (h - 40) / 2,
            40,
            40,
        )
    return c


ZONE = (
    "rounded=1;arcSize=2;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=18;spacingTop=12;"
    + FONT
)
vertex(
    "Users & channels",
    ZONE
    + "fillColor=#FFFFFF;strokeColor=#DADCE0;strokeWidth=1.5;fontSize=19;fontStyle=1;fontColor=#5F6368;",
    0,
    0,
    280,
    700,
)
vertex(
    "Google Cloud",
    ZONE + "fillColor=#F1F3F4;strokeColor=none;fontSize=21;fontStyle=1;fontColor=#202124;",
    300,
    0,
    1490,
    700,
)
vertex(
    "Region · asia-southeast1",
    ZONE
    + "fillColor=#FFFFFF;strokeColor=#9AA0A6;strokeWidth=1.5;dashed=1;dashPattern=6 4;fontSize=16;fontColor=#5F6368;",
    320,
    50,
    990,
    630,
)
ai = vertex(
    label(
        "AI on Google Cloud", "Gemini Enterprise Agent Platform<br>(formerly Vertex AI)", "#1967D2"
    ),
    ZONE
    + "fillColor=#E8F0FE;strokeColor=none;fontSize=20;fontColor=#174EA6;spacingLeft=70;spacingTop=12;",
    1330,
    50,
    440,
    630,
)
vertex("", f"shape=image;aspect=fixed;imageAspect=0;image={ICON['vertexai']};", 1348, 64, 42, 42)

ext_discord = card("Discord", "team text and voice<br>rooms", 18, 110, 228, 104, "discord")
ext_line = card("LINE", "1:1 and group chats,<br>live", 18, 250, 228, 104, "line")
ext_web = card("Web app", "command center, PM,<br>Meet recorder", 18, 390, 228, 104, "web")
SOON = (
    CARD.replace("strokeColor=#DADCE0", "strokeColor=#9AA0A6").replace(
        "fillColor=#FFFFFF", "fillColor=#F8F9FA"
    )
    + "dashed=1;dashPattern=6 4;spacingLeft=16;fontColor=#5F6368;"
)
vertex(
    label("Slack · Telegram · WhatsApp", "bridges built, not yet deployed", "#80868B"),
    SOON,
    18,
    520,
    228,
    80,
)
vertex(
    label("Google Calendar · Gmail · Drive", "planned connectors", "#80868B"),
    SOON,
    18,
    610,
    228,
    80,
)

run_bot = card(
    "Cloud Run",
    "worker pool · dory-bot<br>Discord gateway and voice",
    340,
    110,
    270,
    104,
    "cloud_run",
)
run_line = card(
    "Cloud Run", "service · dory-platforms<br>LINE webhooks", 340, 250, 270, 104, "cloud_run"
)
run_web = card(
    "Cloud Run",
    "service · meeting-scribe<br>web app, APIs, Meet recorder",
    340,
    390,
    270,
    104,
    "cloud_run",
)
brain = vertex(
    '<b style="font-size:28px">Dory brain</b><br>'
    '<font style="font-size:18px" color="#E9E3FB">Google ADK agent, built for each request</font><br><br>'
    '<font style="font-size:17px">• Up to 171 tools: memory, tasks, ledger, meetings, web<br>'
    "• Company, person and audience fixed in code, never by the model<br>"
    "• Meeting minutes: Sequential → Parallel ×3 Flash → Gemini 3.1 Pro<br>"
    "• One brain for Discord, LINE and the web app</font>",
    "rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor=#3B3F99;strokeColor=none;align=left;verticalAlign=middle;spacingLeft=28;spacingRight=16;fontColor=#FFFFFF;fontSize=16;"
    + FONT,
    640,
    110,
    650,
    384,
)
pubsub = card("Pub/Sub", "meeting finalize,<br>push with OIDC", 340, 540, 270, 90, "pubsub")
fs = card(
    "Firestore", "memory, ledger,<br>tasks, orgs", 640, 540, 205, 90, "firestore", "fontSize=16;"
)
gcs = card(
    "Cloud Storage",
    "recordings,<br>receipts, files",
    862.5,
    540,
    205,
    90,
    "cloud_storage",
    "fontSize=16;",
)
card(
    "Secret Manager",
    "bot tokens,<br>webhook URL",
    1085,
    540,
    205,
    90,
    "secret_manager",
    "fontSize=16;",
)

MODEL = (
    "rounded=1;arcSize=10;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#D2E3FC;strokeWidth=1.5;align=left;verticalAlign=middle;spacingLeft=16;fontSize=16;fontColor=#202124;"
    + FONT
)
models = [
    ("Gemini 3.5 Flash · Flash-Lite", "answers and tool calls · fast checks"),
    ("Gemini 3.1 Pro", "meeting synthesis (preview)"),
    ("Gemini Live 2.5 native audio", "real-time voice · us-central1"),
    ("gemini-embedding-001", "memory search by meaning"),
    ("Google Search grounding", "cited web answers · URL context"),
    ("Nano Banana 2.1", "images and promo cards"),
]
for i, (t, s) in enumerate(models):
    vertex(label(t, s), MODEL, 1350, 150 + i * 72, 400, 62)
vertex(
    label("Cloud Text-to-Speech", "Chirp 3 HD voices, Thai included"),
    MODEL + "spacingLeft=56;",
    1350,
    150 + 6 * 72,
    400,
    62,
)
vertex(
    "",
    f"shape=image;aspect=fixed;imageAspect=0;image={ICON['text-to-speech']};",
    1364,
    150 + 6 * 72 + 15,
    32,
    32,
)

LEG = (
    "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontSize=14;fontColor=#5F6368;"
    + FONT
)
vertex(
    "Solid arrow: request  ·  Dashed arrow: asynchronous  ·  Dashed grey card: built but not deployed, or planned",
    LEG,
    340,
    636,
    950,
    36,
)

E = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#5F6368;strokeWidth=2;endArrow=block;endFill=1;endSize=7;fontSize=14;fontColor=#3C4043;labelBackgroundColor=#FFFFFF;"
    + FONT
)
TWO = "startArrow=block;startFill=1;startSize=7;"
edge(ext_discord, run_bot, E + TWO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "gateway")
edge(ext_line, run_line, E + TWO + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "webhook")
edge(ext_web, run_web, E + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;", "HTTPS")
edge(run_bot, brain, E + "exitX=1;exitY=0.5;entryX=0;entryY=0.1354;")
edge(run_line, brain, E + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
edge(run_web, brain, E + "exitX=1;exitY=0.5;entryX=0;entryY=0.8646;")
edge(run_web, pubsub, E + TWO + "dashed=1;exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
edge(brain, fs, E + TWO + "exitX=0.1577;exitY=1;entryX=0.5;entryY=0;", "read / write")
edge(brain, gcs, E + TWO + "exitX=0.5;exitY=1;entryX=0.5;entryY=0;")
edge(brain, ai, E + "strokeColor=#1967D2;strokeWidth=3;exitX=1;exitY=0.5;entryX=0;entryY=0.4;")

xml = (
    '<mxfile><diagram name="Dory architecture"><mxGraphModel dx="0" dy="0" grid="0" page="0" adaptiveColors="none"><root>'
    '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + "".join(cells)
    + "</root></mxGraphModel></diagram></mxfile>"
)
Path(OUT).write_text(xml)
print(OUT, len(xml), "bytes,", n[0], "cells")
