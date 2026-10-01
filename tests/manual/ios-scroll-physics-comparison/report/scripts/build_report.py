# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
# cspell:ignore BOTTOMPADDING FONTNAME FONTSIZE LINEBELOW ROWBACKGROUNDS TEXTCOLOR TOPPADDING pagesizes pdfbase pdfgen pdfmetrics runloop ttfonts
# cspell:ignore reportlab platypus

import argparse
import json
from pathlib import Path
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.utils import ImageReader

font_dir = Path(reportlab.__file__).parent / "fonts"
for suffix, filename in [
    ("", "Vera.ttf"),
    ("-Bold", "VeraBd.ttf"),
    ("-Italic", "VeraIt.ttf"),
    ("-BoldItalic", "VeraBI.ttf"),
]:
    pdfmetrics.registerFont(TTFont("ReportSans" + suffix, str(font_dir / filename)))
pdfmetrics.registerFontFamily(
    "ReportSans",
    normal="ReportSans",
    bold="ReportSans-Bold",
    italic="ReportSans-Italic",
    boldItalic="ReportSans-BoldItalic",
)

parser = argparse.ArgumentParser()
parser.add_argument(
    "--report-dir", type=Path, default=Path(__file__).resolve().parents[1]
)
args = parser.parse_args()
root = args.report_dir
output = root / "REPORT.pdf"
width, height = landscape(A4)
margin = 42
navy = colors.HexColor("#172b4d")
blue = colors.HexColor("#165db0")
red = colors.HexColor("#c53228")
muted = colors.HexColor("#506176")
light = colors.HexColor("#edf3f9")
body = ParagraphStyle(
    "Body", fontName="ReportSans", fontSize=11, leading=16, textColor=navy
)
small = ParagraphStyle("Small", parent=body, fontSize=9, leading=13, textColor=muted)
pdf = canvas.Canvas(str(output), pagesize=(width, height))
pdf.setTitle("UIKit and Slint - Three-Part Scroll Physics Report")
pdf.setAuthor("Slint scroll physics investigation")
page = 0
page_count = 31


def text(value, x, top, available=None, style=body):
    paragraph = Paragraph(value, style)
    _, used = paragraph.wrap(available or width - 2 * margin, height)
    paragraph.drawOn(pdf, x, top - used)
    return top - used - 10


def begin(part, title, subtitle=None):
    global page
    if page:
        pdf.showPage()
    page += 1
    pdf.setFillColor(blue)
    pdf.rect(margin, height - 42, 28, 3, fill=1, stroke=0)
    pdf.setFont("ReportSans-Bold", 9)
    pdf.setFillColor(muted)
    pdf.drawString(margin + 38, height - 41, "UIKIT / SLINT    |    " + part.upper())
    pdf.setFillColor(navy)
    title_size = 25
    while (
        pdfmetrics.stringWidth(title, "ReportSans-Bold", title_size)
        > width - 2 * margin
    ):
        title_size -= 1
    pdf.setFont("ReportSans-Bold", title_size)
    pdf.drawString(margin, height - 80, title)
    y = height - 98
    if subtitle:
        y = text(subtitle, margin, y, style=small)
    pdf.setStrokeColor(colors.HexColor("#d9e3ee"))
    pdf.line(margin, 34, width - margin, 34)
    pdf.setFillColor(muted)
    pdf.setFont("ReportSans", 8)
    platform = "Physical iPhone" if page <= 13 else "Phone / simulator follow-up"
    pdf.drawString(
        margin,
        21,
        f"October 1, 2026  |  {platform}  |  Release  |  Source baseline 5e0f6d10f1",
    )
    pdf.drawRightString(width - margin, 21, f"{page} / {page_count}")
    return y


def table(rows, top, widths=None):
    grid = Table(
        rows, colWidths=widths or [(width - 2 * margin) / len(rows[0])] * len(rows[0])
    )
    grid.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "ReportSans-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "ReportSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (0, 1), (-1, -1), navy),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [light, colors.white]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#d9e3ee")),
            ]
        )
    )
    _, used = grid.wrap(width - 2 * margin, height)
    grid.drawOn(pdf, margin, top - used)
    return top - used - 16


def figure(part, title, name, subtitle):
    begin(part, title, subtitle)
    image = ImageReader(str(root / "figures" / name))
    iw, ih = image.getSize()
    scale = min((width - 2 * margin) / iw, (height - 188) / ih)
    w, h = iw * scale, ih * scale
    pdf.drawImage(
        image,
        (width - w) / 2,
        53 + (height - 188 - h) / 2,
        width=w,
        height=h,
        mask="auto",
    )


begin("Three-part report", "UIKit and Slint: Scroll Physics")
y = text(
    "A physical comparison of pan entry, overscroll pulling, and return animation, "
    "with a simulator follow-up.",
    margin,
    height - 125,
)
y = text(
    "<b>Measured progress:</b> the pull mapping matches the three tested exposure peaks closely. "
    "The changed spring is much closer, but still does not match the full UIKit curve.",
    margin,
    y,
)
card_y = height - 305
card_w = (width - 2 * margin - 28) / 3
cards = [
    ("0.069 pt", "Pull peak gap at 200 points", blue),
    ("40.18 to 7.76 pt", "600-point return gap, before / candidate", blue),
    ("NOT MATCHED", "Spring criterion still fails", red),
]
for index, (value, label, color) in enumerate(cards):
    x = margin + index * (card_w + 14)
    pdf.setFillColor(light)
    pdf.roundRect(x, card_y, card_w, 95, 8, fill=1, stroke=0)
    pdf.setFillColor(color)
    pdf.setFont("ReportSans-Bold", 23 if index != 1 else 20)
    pdf.drawString(x + 15, card_y + 55, value)
    text(label, x + 15, card_y + 36, card_w - 30, small)
y = card_y - 22
for title, detail in [
    (
        "01  Before changes",
        "Original behavior, event dispatch, and a separate manual recording.",
    ),
    (
        "02  Fixing the pull",
        "A 10-point threshold and absolute rubber-band mapping, tested in code.",
    ),
    (
        "03  The return animation",
        "Candidate spring, release-state controls, and natural collisions after finger lift.",
    ),
]:
    y = text("<b>" + title + "</b> - " + detail, margin, y)
y = text(
    "Murmele/slint, branch nigel/ios-uikit-scroll-parity. Draft PR #7. "
    "No chart rescales distance or duration. Raw per-event recordings remain local.",
    margin,
    y,
    style=small,
)
pdf.setFillColor(blue)
pdf.setFont("ReportSans-Bold", 10)
pdf.drawString(margin, 57, "Share the current work: github.com/Murmele/slint/pull/7")
pdf.linkURL(
    "https://github.com/Murmele/slint/pull/7",
    (margin, 53, margin + 340, 68),
    relative=0,
)

y = begin("Part 1 - Before changes", "The original behavior and the measurement")
y = text(
    "The app overlays a translucent native UIScrollView on a Slint ScrollView and forwards the "
    "original touch objects and event to Slint. Both views have matching 408 x 774-point viewports "
    "and 400 x 72000-point content, with 72-point rows.",
    margin,
    y,
)
y = text(
    "The physical iPhone 13 Pro Max runs iOS 27.0. The build uses Release, Cupertino style, "
    "and Winit/Skia. The automated position sampler delivered about 120 Hz: median intervals near "
    "8.335 ms. A point is three physical pixels on this phone. Sampling rate is not renderer FPS.",
    margin,
    y,
)
y = text(
    "Original Slint subtracts 8 points and applies overscroll friction to each event delta. "
    "The current exposure affects the next delta, and a first boundary crossing can pass through "
    "unresisted. Event batching can therefore change the retained exposure.",
    margin,
    y,
)
y = table(
    [
        ["Original 120 Hz capture", "UIKit peak exposure", "Slint peak exposure"],
        ["50-point pull", "21.333 pt", "21.567 pt"],
        ["200-point pull", "92.000 pt", "89.352 pt"],
        ["600-point pull", "228.667 pt", "221.033 pt"],
    ],
    y,
)
y = text(
    "UIKit also discarded more initial movement. Held paths consumed 10 points in UIKit and "
    "8 in Slint; immediate earlier paths consumed 10-15.333 points in UIKit. That is discarded "
    "movement, not proof of a universal recognition threshold.",
    margin,
    y,
)
text(
    "Recognition and action dispatch are distinct. Apple documents the began action on the next "
    "run-loop cycle. Disabling forwarding to Slint did not remove the extra loss, although recording "
    "and scheduling effects are not completely excluded.",
    margin,
    y,
    style=small,
)

figure(
    "Part 1 - Before changes",
    "Original automated pull and return",
    "baseline-pull-and-return.png",
    "Actual position samples from the physical phone, paired within each capture.",
)
figure(
    "Part 1 - Before changes",
    "A separate real-finger recording",
    "manual-before-changes.png",
    "Earlier 60 Hz manual capture: 45.418-point largest gap; UIKit / Slint settling about 0.642 / 0.742 s.",
)

y = begin("Part 2 - Fixing the pull", "From event-by-event friction to a distance map")
y = text(
    "The pull candidate uses 10 points for the iOS threshold and maps the underlying drag "
    "distance into visible exposure. Each event inverts the current exposure, adds the new finger "
    "delta, then applies the same map. Large batches and small steps have the same mathematical result.",
    margin,
    y,
)
pdf.setFillColor(light)
pdf.roundRect(margin, y - 54, width - 2 * margin, 48, 7, fill=1, stroke=0)
pdf.setFillColor(blue)
pdf.setFont("ReportSans-Bold", 15)
pdf.drawString(
    margin + 18,
    y - 34,
    "exposure = 0.55 x distance x viewport / (viewport + 0.55 x distance)",
)
y -= 76
y = text(
    "The coefficient was proposed from the 200-point capture. The 50- and 600-point pulls were "
    "checks outside that calibration distance. No mode uses UIKit positions to drive Slint.",
    margin,
    y,
)
y = table(
    [
        ["Delivered pull", "UIKit", "Modified Slint", "Absolute peak gap"],
        ["50 pt", "21.333 pt", "21.392 pt", "0.059 pt"],
        ["200 pt", "92.000 pt", "92.069 pt", "0.069 pt"],
        ["600 pt", "228.667 pt", "228.642 pt", "0.025 pt"],
    ],
    y,
)
y = text(
    "A unit test checks batching independence and reversals at both bounds. On the explicitly "
    "held 40-point pan, the threshold change removed the 2-point gap in both repeats, including "
    "zero sampled contact separation.",
    margin,
    y,
)
text(
    "Immediate paths still diverged. A numeric threshold change alone does not reproduce UIKit's "
    "deferred baseline handling. Each chart panel compares its own paired UIKit and Slint data; "
    "requested waypoints are not delivered event counts.",
    margin,
    y,
    style=small,
)

figure(
    "Part 2 - Fixing the pull",
    "Improved exposure; original spring still diverges",
    "modified-pull-and-return.png",
    "The pull mapping is closely matched. These captures still use the original return spring.",
)
figure(
    "Part 2 - Fixing the pull",
    "Threshold change: two repeated captures",
    "pan-before-after.png",
    "Held entry aligns here; immediate entry remains different. Every panel contains both implementations.",
)

y = begin(
    "Part 3 - Return animation", "A closer spring, with visible failed predictions"
)
y = text(
    "The original spring evolves the displayed exposure directly, with mass 0.5, stiffness 100, "
    "damping ratio 1.1, and zero initial velocity. Matching the pull leaves a large return error.",
    margin,
    y,
)
y = text(
    "The candidate evolves spring travel in the underlying drag coordinate and maps that travel "
    "back to the display. It retains the mass, stiffness, and damping parameters. An empirical "
    "initial-return rate of 2.4422646 per second was calibrated from the 200-point trace.",
    margin,
    y,
)
y = table(
    [
        ["Delivered pull", "Original spring maximum gap", "Candidate maximum gap"],
        ["50 pt", "2.549 pt", "1.167 pt"],
        ["200 pt", "10.269 pt", "2.458 pt"],
        ["600 pt", "40.177 pt", "7.760 pt"],
    ],
    y,
)
y = text(
    "The model is a candidate black-box approximation, not a claim about UIKit private code. "
    "Unseen 100-, 300-, and 450-point paths were each repeated twice. They retained maximum "
    "errors of 1.20-1.89, 3.76-4.02, and 6.97-7.20 points respectively.",
    margin,
    y,
)
y = text(
    "<b>The criterion still fails:</b> at most 0.5 points throughout return in every complete "
    "trace. The spring is improved, not solved. The early-frame residual remains important even "
    "when the later curves look close.",
    margin,
    y,
)
text(
    "The final clock control starts the same model from live backend time. It worsened return RMS "
    "error in both repeats at both tested distances and is retained as a rejected control.",
    margin,
    y,
    style=small,
)

figure(
    "Part 3 - Return animation",
    "Changed code: return before and after",
    "spring-before-after.png",
    "Both rows use the improved pull mapping. The remaining candidate gap is shown at actual scale.",
)
figure(
    "Part 3 - Return animation",
    "Independent validation paths",
    "spring-holdouts.png",
    "Three distances outside the calibration path, repeated twice. Failures remain in the published aggregates.",
)
figure(
    "Part 3 - Return animation",
    "Zoom into the early release residual",
    "early-release-detail.png",
    "Actual first 60 ms; the axes are not normalized or shifted to force alignment.",
)
figure(
    "Part 3 - Return animation",
    "Phone follow-up: testing the release clock",
    "release-clock-check.png",
    "Animation-tick start versus live backend clock start, each paired with UIKit and repeated twice.",
)

y = begin("Part 3 - Evidence and limits", "What remains needed for a complete match")
y = table(
    [
        [
            "Fixed 0-0.8 s return window",
            "Animation-tick RMS, repeats 1 / 2",
            "Live-clock RMS, repeats 1 / 2",
        ],
        ["200-point pull", "0.712 / 0.771 pt", "1.014 / 0.784 pt"],
        ["600-point pull", "1.481 / 1.682 pt", "1.864 / 1.818 pt"],
    ],
    y,
)
y = text(
    "The recorder saw 400-409 ms of clock age before forwarding release after the hold, but "
    "only 1.375-2.724 ms at UIKit's ended action after processing. These are different dispatch "
    "observations, not clock age at spring construction. They do not support a 400 ms stale "
    "clock explanation.",
    margin,
    y,
)
y = text(
    "<b>Remaining work:</b> reproduce recognized pan dispatch and the first retained movement; "
    "separate animation handoff from display-phase timing; preserve measured release state in the spring; "
    "validate bottom bounds, interrupted springs, and carried momentum independently. Native pan "
    "state, translation, and velocity are available from UIPanGestureRecognizer, but that backend "
    "approach has not been verified here.",
    margin,
    y,
)
y = text(
    "<b>Original two rounds:</b> 44 complete automated captures, plus the separate manual "
    "capture. Delivered distances, explicit initial holds, and actual sampling intervals were checked. "
    "Five spring unit tests and the rubber-band batching/reversal test passed. Green UI tests mean "
    "both views received the gesture and settled, not that physics match.",
    margin,
    y,
)
y = text(
    "The repository includes the source app, selected tests, figures, written predictions, "
    "aggregate CSV/JSON results, and plotting code. Raw per-event touch recordings and xcresult "
    "bundles remain local. The first inconsistent threshold attempt is preserved locally and "
    "excluded from the reported successful code comparisons.",
    margin,
    y,
)
text(
    "Read FINDINGS.md and README.md in tests/manual/ios-scroll-physics-comparison. "
    "The report cites Apple documentation for pan states, translation, velocity, and deferred began "
    "dispatch. No Flutter claim is used as evidence of UIKit parity.",
    margin,
    y,
    style=small,
)

results = json.loads((root / "evidence" / "simulator-summary.json").read_text())
variants = [
    "spring-coordinate",
    "spring-runloop",
    "spring-zero-velocity",
    "spring-history",
]
names = [
    "Current candidate",
    "Deferred release",
    "Zero initial spring velocity",
    "Direct touch time/history",
]
y = begin("Part 3 - Simulator follow-up", "New alternatives without using the phone")
y = text(
    "The iPhone 18 Pro Simulator runs iOS 27.0 in Release with the same Cupertino/Skia app. "
    "Its viewport is 382 x 722 points and the position sampler delivers about 60 Hz. "
    "Each alternative has two 200-point and two 600-point pulls. "
    "The simulator is compared against its own UIKit reference, not against the phone curves.",
    margin,
    y,
)
rows = [
    [
        "Spring / delivery mode",
        "200-point RMS, repeats 1 / 2",
        "600-point RMS, repeats 1 / 2",
    ]
]
for variant, name in zip(variants, names):
    values = []
    for distance in [200, 600]:
        cell = sorted(
            [
                r
                for r in results
                if r["variant"] == variant and r["requested_distance_pt"] == distance
            ],
            key=lambda r: r["trial"],
        )
        values.append(
            "Invalid release"
            if variant == "spring-runloop"
            else " / ".join(f"{r['return_rms_0_8_s_pt']:.3f}" for r in cell) + " pt"
        )
    rows.append([name] + values)
y = table(rows, y)
qualified = sum(r["qualified_for_physics"] for r in results)
matched = sum(r["full_return_within_0_5_pt"] for r in results)
y = text(
    f"<b>Qualification:</b> {qualified} of {len(results)} traces have a complete gesture and settled return, "
    "the requested distance delivered within 0.5 points, and no return sample gap above 30 ms. "
    f"{matched} traces meet the 0.5-point full-return criterion. "
    "Every graph uses actual release callback time and unscaled points.",
    margin,
    y,
)
y = text(
    "The deferred-release mode lost Slint release delivery in all four traces; its flat curves are invalid "
    "for spring comparison. Zero velocity tests the fitted initial spring kick. "
    "Direct touch delivery preserves UIKit sample times and coalesced positions that the Winit "
    "adapter drops. It also refreshes timers and changes dispatch route, so a route control is "
    "required before attributing any difference to history alone.",
    margin,
    y,
)
text(
    "The core still drops the release timestamp when it constructs the pointer release. "
    "These diagnostic modes do not change normal defaults and do not establish physical-phone parity. "
    "All predictions and per-gesture aggregates are retained, including failures.",
    margin,
    y,
    style=small,
)

figure(
    "Part 3 - Simulator follow-up",
    "Test release ordering against the current spring",
    "simulator-release-order.png",
    "Two repeats at each distance, each with its own UIKit reference. No time alignment shift.",
)
figure(
    "Part 3 - Simulator follow-up",
    "Test initial velocity and preserved touch samples",
    "simulator-velocity-and-history.png",
    "Zero spring kick and direct touch history are independent diagnostics. Both list positions appear in every panel.",
)

y = begin("Part 3 - Release momentum", "Immediate release, exact hold, and quiet stop")
y = text(
    "New captures use 100- and 600-point pulls, two velocity settings (400 and 1600), "
    "immediate release or a delivered 400 ms hold, and two repeats on each platform. "
    "Velocity settings label the requested API input; measured speeds are retained separately in points/s. "
    "A quiet-stop control adds a one-physical-pixel slow finish before release.",
    margin,
    y,
)
y = table(
    [
        ["Campaign", "Gesture and sampling qualified", "Total"],
        ["Physical phone, public drag API", "16", "16"],
        ["Physical phone, quiet stop", "4", "4"],
        ["Simulator, public drag API", "14", "16"],
        ["Simulator, quiet stop", "3", "4"],
    ],
    y,
)
y = text(
    "<b>Observation:</b> the fast 100-point phone pulls continue outward after release by 28 points "
    "without a hold, and 33.33-39.67 points after an exact 400 ms hold. Slint adds zero outward travel. "
    "During the exact hold, UIKit's pan recognizer still reports a cached nonzero velocity. "
    "The quiet-stop control refreshes that estimate to about -1.336 points/s and adds no outward travel.",
    margin,
    y,
)
y = text(
    "Slint's outside-bounds release calls spring_back without passing estimated release velocity. "
    "Its estimator also treats motion older than 40 ms as stopped. These source facts explain why "
    "one fixed return curve cannot cover the observed release states. They do not prove that UIKit "
    "changes spring coefficients: different initial velocities and nonlinear resistance can change the curve.",
    margin,
    y,
)
text(
    "37/40 traces pass the predeclared 30 ms maximum sample-gap rule. Failed traces remain visible. "
    "Starting exposure sometimes differs because pan entry is unresolved, so return error includes that gap. "
    "A still hold is not a verified zero-velocity native spring. The earlier dense injector compressed "
    "requested timing and is excluded from this matrix.",
    margin,
    y,
    style=small,
)
for platform, label in [("phone", "Physical iPhone"), ("simulator", "Simulator")]:
    for mode, description in [
        ("public", "Immediate release / exact hold"),
        ("quiet", "Quiet-stop control"),
    ]:
        for distance in [100, 600]:
            figure(
                "Part 3 - Release momentum",
                f"{label}: {description}, {distance} points",
                f"{platform}-{mode}-release-d{distance}.png",
                "UIKit red, Slint blue. Actual exposure and common release time; both repeats retained.",
            )

y = begin("Part 3 - Free-flight collision", "Hit the top after the finger lifts")
y = text(
    "Both lists start at item 10 (offset 648 points). A downward 200-point finger path moves toward "
    "the start of the full 1000-row list. Each of six velocity settings runs twice in a fresh launch. "
    "The finger must lift with both offsets still positive. The slow setting is a no-hit control.",
    margin,
    y,
)
y = text(
    "Slint's in-bounds fling transfers measured model velocity into the existing collision spring. "
    "This is a separate path from releasing a finger already outside the bounds. "
    "The new test records natural free deceleration, the first edge crossing, peak background exposure, "
    "return, and settling. It does not copy native positions or velocities into Slint.",
    margin,
    y,
)

y = text(
    "<b>Result:</b> all 12 phone traces and 11 of 12 simulator traces qualify. "
    "The simulator's first slow control has a 33.11 ms sampling gap and is excluded. "
    "Settings 1500 and above produce clear top collisions after release on both platforms.",
    margin,
    y,
)
y = text(
    "In the eight phone collisions, Slint peaks earlier and settles 74-112 ms earlier than UIKit. "
    "Its fitted approach speed is higher, yet seven of eight peaks expose less background. "
    "The second 4500-setting repeat has nearly equal peaks but still different return timing. "
    "Both approach and collision response therefore need attention. Native phone release offsets "
    "range from 458 to 523 points; Slint releases at 458. The shared gesture does not force equal "
    "release poses or incoming velocities. An equal-state control is needed to isolate spring coefficients.",
    margin,
    y,
)
text(
    "The simulator's repeated 3000 settings delivered substantially different behavior. "
    "Requested settings are not identical measured momentum. A 0.093-point Slint crossing at setting "
    "1000 is retained as unresolved below the 0.5-point amplitude criterion. "
    "These observations do not identify UIKit's private spring constants or prove that they change.",
    margin,
    y,
    style=small,
)

y = begin(
    "Part 3 - Free-flight collision",
    "Top-boundary collision measurements",
    "Ranges cover both repeats passing gesture and sampling guards; requested settings are not measured speeds.",
)
collision_rows = [
    ["Platform / setting", "UIKit / Slint peak (pt)", "UIKit / Slint settle (s)"]
]
for platform in ["phone", "simulator"]:
    collision_results = json.loads(
        (root / "evidence" / f"{platform}-top-collision-summary.json").read_text()
    )
    for setting in [400, 1000, 1500, 2200, 3000, 4500]:
        cell = [r for r in collision_results if r["velocity_setting"] == setting]

        def span(side, key):
            if (
                key == "impact_to_settled_s"
                and any(r[side].get("hit") for r in cell)
                and not any(r[side].get("overscroll_resolved_at_0_5_pt") for r in cell)
            ):
                return "unresolved"
            if not any(
                r["gesture_qualified"] and r["sampling_qualified"] for r in cell
            ):
                return "unqualified"
            values = [
                r[side].get(key)
                for r in cell
                if r["gesture_qualified"] and r["sampling_qualified"]
            ]
            values = [v for v in values if v is not None]
            return "no hit" if not values else f"{min(values):.2f}-{max(values):.2f}"

        collision_rows.append(
            [
                f"{platform} / {setting}",
                span("uikit", "peak_overscroll_pt")
                + " / "
                + span("slint", "peak_overscroll_pt"),
                span("uikit", "impact_to_settled_s")
                + " / "
                + span("slint", "impact_to_settled_s"),
            ]
        )
y = table(collision_rows, y)
text(
    "Settling is measured from each observed impact to staying within 0.5 points. "
    "The charts retain one common release clock and do not align impacts. "
    "Sub-0.5-point edge excursions are marked unresolved in the evidence. "
    "Measured impact speeds and sample counts are in the aggregate JSON; missing speed estimates are explicit. "
    "In-bounds flings use the existing IOsFlick collision spring, not the outside-release spring candidate.",
    margin,
    y,
    style=small,
)
for platform, label in [("phone", "Physical iPhone"), ("simulator", "Simulator")]:
    for detail, description in [
        ("flight", "Free flight and top collision"),
        ("bounce", "Top bounce detail"),
    ]:
        figure(
            "Part 3 - Free-flight collision",
            f"{label}: {description}",
            f"{platform}-top-collision-{detail}.png",
            "Item 10, downward flick, finger up before impact. UIKit red, Slint blue; actual points and seconds.",
        )

assert page == page_count
pdf.save()
print(output)
