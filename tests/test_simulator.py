from app.simulator.generator import GenConfig, Generator


def test_generator_produces_all_families_and_scenarios():
    cfg = GenConfig(seed=7, days=5, employees_per_role={
        "engineering": 3, "finance": 2, "hr": 2, "operations": 2})
    result = Generator(cfg).run()

    for fam in ("login", "file_access", "usb", "process", "print", "email_metadata"):
        assert len(result["events"][fam]) > 0, fam

    scenarios = result["manifest"]["scenarios"]
    assert len(scenarios) >= 4
    ids = {s["scenario_id"] for s in scenarios}
    assert any(i.startswith("S1") for i in ids)

    # every scenario event id must exist in the generated events
    all_ids = {r["event_id"] for fam in result["events"].values() for r in fam}
    for s in scenarios:
        assert set(s["event_ids"]).issubset(all_ids), s["scenario_id"]


def test_generator_deterministic():
    cfg = GenConfig(seed=3, days=4, employees_per_role={
        "engineering": 2, "finance": 2, "hr": 1, "operations": 1})
    r1 = Generator(cfg).run()
    r2 = Generator(cfg).run()
    assert [e["event_id"] for e in r1["events"]["login"]] == \
           [e["event_id"] for e in r2["events"]["login"]]