import json
import zipfile
import pytest
from discover.engine.cli import main
from discover.engine.personas.engine import IntakeError, analyse

PHONE = ["segments", "--name", "Budget phone", "--description", "Affordable phone with long battery life for students",
         "--category", "smartphone", "--price", "40000", "--currency", "NGN", "--location", "Lagos", "--feature", "dual sim"]


def test_engine_rejects_invalid_intake(make_intake, store):
    with pytest.raises(IntakeError) as e:
        analyse(make_intake(price=-5, category="x"), store)
    assert len(e.value.errors) >= 2


def test_engine_output_shape_and_labels(make_intake, store):
    res = analyse(make_intake(price=100, currency="USD"), store)
    assert set(res) == {"intake", "affordability", "segments", "attribution", "labels"}
    assert any("World Bank" in a for a in res["attribution"]) and any("ExchangeRate-API" in a for a in res["attribution"])
    assert "not a probability" in res["labels"]["score"]
    json.dumps(res)


def test_engine_no_fx_attribution_when_no_conversion(make_intake, store):
    assert not any("ExchangeRate" in a for a in analyse(make_intake(), store)["attribution"])


def test_cli_segments_writes_run_folder_and_zip(tmp_path, capsys):
    code = main([*PHONE, "--cache", str(tmp_path / "c.json"), "--out", str(tmp_path / "runs")])
    out = capsys.readouterr().out
    assert code == 0 and "Affordability tier" in out and "send me" in out
    run = next((tmp_path / "runs").glob("*_segments_budget-phone"))
    assert {p.name for p in run.iterdir()} == {"00_input.json", "01_result.json", "02_summary.md"}
    res = json.loads((run / "01_result.json").read_text())
    assert res["affordability"]["tier"] == "budget" and res["segments"]["ranked"]
    z = next((tmp_path / "runs").glob("*.zip"))
    assert any(n.endswith("02_summary.md") for n in zipfile.ZipFile(z).namelist())


def test_cli_segments_from_file(tmp_path, capsys):
    f = tmp_path / "in.json"
    f.write_text(json.dumps({"name": "Pro phone", "description": "Flagship phone with a great camera and chip",
                             "category": "smartphone", "price": 1500, "currency": "USD", "location": "New York", "max_personas": 3}))
    code = main(["segments", "--file", str(f), "--cache", str(tmp_path / "c.json"), "--out", str(tmp_path / "r"), "--no-zip"])
    assert code == 0
    res = json.loads(next((tmp_path / "r").glob("*/01_result.json")).read_text())
    assert len(res["segments"]["ranked"]) <= 3 and res["affordability"]["country"] == "USA"


def test_cli_reports_invalid_intake(tmp_path, capsys):
    code = main(["segments", "--name", "x", "--cache", str(tmp_path / "c.json"), "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 3 and "intake problems" in out and "category" in out


def test_cli_reports_missing_reference_data(tmp_path, capsys):
    argv = [a if a != "Lagos" else "Nairobi" for a in PHONE]
    argv = [("KES" if a == "NGN" else a) for a in argv]
    code = main([*argv, "--cache", str(tmp_path / "c.json"), "--out", str(tmp_path)])
    assert code == 3 and "refresh" in capsys.readouterr().out


def test_cli_bad_file_is_handled(tmp_path, capsys):
    f = tmp_path / "bad.json"
    f.write_text("{nope")
    assert main(["segments", "--file", str(f), "--cache", str(tmp_path / "c.json")]) == 3


def test_cli_refdata_show(tmp_path, capsys):
    assert main(["refdata", "show", "--country", "NGA", "--cache", str(tmp_path / "c.json")]) == 0
    out = capsys.readouterr().out
    assert "NY.GNP.PCAP.CN" in out and "1,800,770.86" in out and "FX records" in out


def test_cli_refdata_refresh_rejects_unsupported_country(tmp_path, capsys):
    assert main(["refdata", "refresh", "--country", "XXX", "--cache", str(tmp_path / "c.json")]) == 3
    assert "unsupported" in capsys.readouterr().out
