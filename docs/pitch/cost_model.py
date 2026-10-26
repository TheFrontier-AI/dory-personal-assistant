"""Dory monthly cost model: official prices (18-19 Oct 2026) x stated assumptions. Prints a markdown table."""

M = 1e6
P = dict(
    fl_in=1.50,
    fl_cache=0.15,
    fl_out=9.00,
    lite_in=0.30,
    lite_out=2.50,
    pro_in=2.00,
    pro_out=12.00,
    live_ain=3.00,
    live_aout=12.00,
    img_1k=0.034,
)
SEC = 730 * 3600  # seconds in an average month


def infra():
    # The free tier is a spending-based discount at Tier 1 (us-central1) prices: $5.22/month per kind.
    wp_list = SEC * 0.000013493 + 2 * SEC * 0.000001482  # worker pool dory-bot: 1 vCPU, 2 GiB
    wp_free = wp_list - (384204 * 0.000011244 + 728744 * 0.000001235)
    # Service dory-platforms (LINE): min 1 instance, CPU always allocated = instance-based, 1 vCPU, 1 GiB
    line_list = SEC * 0.0000216 + SEC * 0.0000024
    line_free = line_list - (240000 * 0.000018 + 450000 * 0.000002)
    return wp_list, wp_free, line_list, line_free


S = {  # people=20; workdays=22
    "Low": dict(
        q_pp=2,
        calls=2,
        tok_in=10_000,
        cached=0.6,
        out=500,
        msgs=150,
        briefs=1,
        meet_h=8,
        live_min=5,
        meet_rec_h=2,
        imgs=10,
    ),
    "Base": dict(
        q_pp=5,
        calls=3,
        tok_in=20_000,
        cached=0.6,
        out=500,
        msgs=300,
        briefs=2,
        meet_h=17,
        live_min=20,
        meet_rec_h=4,
        imgs=20,
    ),
    "High": dict(
        q_pp=10,
        calls=4,
        tok_in=40_000,
        cached=0.5,
        out=750,
        msgs=600,
        briefs=2,
        meet_h=35,
        live_min=60,
        meet_rec_h=8,
        imgs=200,
    ),
}


def run(a, people=20, days=22):
    r = {}
    q = a["q_pp"] * people * days
    per_q = (
        a["calls"]
        * (
            a["tok_in"] * (1 - a["cached"]) * P["fl_in"]
            + a["tok_in"] * a["cached"] * P["fl_cache"]
            + a["out"] * P["fl_out"]
        )
        / M
    )
    r["Chat answers (Gemini 3.5 Flash)"] = q * per_q
    updates = a["msgs"] * 30 / 20  # one summary update per ~20 messages incl. quiet-time passes
    r["Memory, tasks, people (Flash-Lite)"] = (
        updates * (20_000 * P["lite_in"] + 1_900 * P["lite_out"]) / M
    )
    r["Morning/evening briefs (Flash)"] = (
        a["briefs"] * people * days * (8_000 * P["fl_in"] + 400 * P["fl_out"]) / M
    )
    sec = a["meet_h"] * 3600
    r["Voice meetings: transcript + minutes (Flash)"] = (
        sec * 32 * P["fl_in"]
        + sec / 12 * 500 * P["fl_in"]
        + sec / 60 * 150 * P["fl_out"]
        + a["meet_h"] * 30_000 * P["fl_in"]
    ) / M
    lsec = a["live_min"] * 60 * days
    r["Live voice (Gemini Live, context re-billed x3)"] = (
        lsec * 25 * 3 * P["live_ain"] + lsec * 0.3 * 25 * P["live_aout"]
    ) / M
    ms = a["meet_rec_h"] * 3600
    r["Meet recorder: transcript + 3.1 Pro minutes"] = (
        ms * 32 * P["fl_in"]
        + a["meet_rec_h"] * (3 * 40_000 * P["fl_in"] + 40_000 * P["pro_in"] + 2_000 * P["pro_out"])
    ) / M
    r["Images (Nano Banana 2.1, 1K)"] = a["imgs"] * P["img_1k"]
    r["Search grounding, TTS, embeddings"] = (
        0.0  # within free tiers at these volumes (5,000 queries; 1M TTS chars)
    )
    return r, q, per_q


wp_list, wp_free, line_list, line_free = infra()
fixed = {
    "Cloud Run worker pool (1 vCPU, 2 GiB, 24/7)": wp_free,
    "LINE bridge: Cloud Run service dory-platforms (1 vCPU, 1 GiB, always on)": line_free,
    "Cloud Run service, Firestore, Storage, Pub/Sub, Secrets, Registry": 3.0,
}
out = ["| Line item | Low | Base | High |", "|---|---:|---:|---:|"]
res = {k: run(v) for k, v in S.items()}
for item in res["Base"][0]:
    out.append(f"| {item} | " + " | ".join(f"${res[k][0][item]:,.0f}" for k in S) + " |")
for item, v in fixed.items():
    out.append(f"| {item} | ${v:,.0f} | ${v:,.0f} | ${v:,.0f} |")
tot = {k: sum(res[k][0].values()) + sum(fixed.values()) for k in S}
out.append(
    "| **Total per month (20-person company)** | "
    + " | ".join(f"**${tot[k]:,.0f}**" for k in S)
    + " |"
)
out.append("| Per person per month | " + " | ".join(f"${tot[k] / 20:,.2f}" for k in S) + " |")
out.append(
    "| Total in THB (33.541/USD) | " + " | ".join(f"฿{tot[k] * 33.541:,.0f}" for k in S) + " |"
)
print("\n".join(out))
print(
    f"\nWorker pool list price ${wp_list:.2f}/mo, after free tier ${wp_free:.2f}. LINE service ${line_list:.2f}, after free tier ${line_free:.2f}. Chat cost per question: "
    + ", ".join(f"{k} ${res[k][2]:.3f} ({res[k][1]:,} q/mo)" for k in S)
)
assert 30 < wp_list < 50 and all(tot["Low"] < tot["Base"] < tot["High"] for _ in [0])
