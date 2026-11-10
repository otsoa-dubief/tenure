"""The README's guarantee numbers come from params; forbidden wording stays out; the manifest declares what it reads."""
import pathlib

from clearance import params

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
MANIFEST = (ROOT / "clearance" / "plugin.yaml").read_text(encoding="utf-8")
CLAIM = "the same rule as a preregistered study, replayed on 6,000+ simulated agents"


def _cell(d):
    if d["capped"]:
        return "always asks"
    return f"{d['n']} approvals · {d['aoql'] * 100:.1f}% · worst {d['worst_case'] * 100:.1f}%"


def test_guarantee_table_matches_params():
    for preset in ("careful", "balanced", "fast"):
        d = params.describe(preset)
        name = f"**{preset}** (default)" if preset == "balanced" else preset
        row = f"| {name} | " + " | ".join(_cell(d[lv]) for lv in ("low", "medium", "high")) + " |"
        assert row in README, row


def test_forbidden_words_absent():
    low = README.lower()
    for word in ("tamper-proof", "unforgeable", "proven by the study"):
        assert word not in low
    assert "tamper-evident" in low


def test_allowed_study_claim_verbatim_with_layers():
    assert CLAIM in README
    assert "Carry-over is our addition; strict mode is the study." in README
    for layer in ("spot checks", "two distinct sessions", "suspension"):
        assert layer in README
    study = (ROOT / "docs" / "the-study.md").read_text(encoding="utf-8")
    assert CLAIM in study and "results pending" in study.lower()
    assert "does not claim that the study has confirmed the rule" in study.lower()


def test_readme_references_real_files_and_commands():
    for ref in ("docs/protocol.md", "docs/the-study.md", "clearance/NOTICE"):
        assert (ROOT / ref).exists()
        assert ref in README
    for img in ("models", "map", "passport", "mobile"):
        assert f"docs/images/dashboard-{img}.png" in README
    from clearance import cli
    import re
    subs = set(re.findall(r'subs\.add_parser\("(\w+)"', pathlib.Path(cli.__file__).read_text()))
    for s in subs:
        assert f"hermes clearance {s}" in README, s


def test_manifest():
    assert "\nversion: 1.0.0\n" in MANIFEST
    assert '\nrequires_hermes: ">=0.23.0"\n' in MANIFEST
    assert "tamper-proof" not in MANIFEST.lower()
    assert (ROOT / "clearance" / "dashboard" / "manifest.json").exists()      # the dashboard is declared there
    assert "profiles/*" in README and "snapshot" in README                    # the reads disclosure


def test_notice_attributes_epoch_ai():
    n = (ROOT / "clearance" / "NOTICE").read_text(encoding="utf-8")
    assert "Epoch AI" in n and "CC BY 4.0" in n
