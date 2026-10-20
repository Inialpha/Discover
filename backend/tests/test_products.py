"""Products and runs: grouping, run again with changes, the 'what changed' lines, ownership and deletion."""

from discover.api.services.products import diff_intake
from tests.test_api import INTAKE, client, signup, wait  # noqa: F401  (client is a fixture)


def run(c, h, intake=None, **extra):
    r = c.post("/api/analyses", json={"intake": intake or INTAKE, **extra}, headers=h)
    assert r.status_code == 202, r.text
    wait(c, h, r.json()["id"])
    return r.json()


def test_diff_lines_are_readable():
    a = {**INTAKE, "features": [], "competitors": ["Tecno"]}
    assert diff_intake(None, a) == []
    assert diff_intake(a, dict(a)) == []
    assert diff_intake(a, {**a, "price": 45000}) == ["price 40,000 → 45,000 NGN"]
    assert diff_intake(a, {**a, "location": "Abuja", "competitors": ["Tecno", "Infinix"]}) == ["location Lagos → Abuja", "competitors Tecno → Tecno, Infinix"]
    assert diff_intake(a, {**a, "price": 40000.0, "features": []}) == []  # 40000 vs 40000.0 is not a change
    assert diff_intake(a, {**a, "currency": "USD", "price": 50}) == ["price 40,000 NGN → 50 USD"]


def test_first_run_creates_a_product_and_run_again_adds_a_run(client):
    h = signup(client)
    first = run(client, h)
    assert first["run_number"] == 1
    second = run(client, h, {**INTAKE, "price": 45000}, product_id=first["product_id"])
    assert second["product_id"] == first["product_id"] and second["run_number"] == 2
    third = run(client, h, {**INTAKE, "location": "Abuja"}, product_id=first["product_id"], based_on=first["id"])
    assert third["run_number"] == 3

    a2 = client.get(f"/api/analyses/{second['id']}", headers=h).json()
    assert a2["changes"] == ["price 40,000 → 45,000 NGN"] and a2["run_number"] == 2 and a2["run_count"] == 3 and a2["product_name"] == "Zip 5"
    a3 = client.get(f"/api/analyses/{third['id']}", headers=h).json()
    assert a3["changes"] == ["location Lagos → Abuja"]  # shown against run 1 (whose price is the same), not against run 2

    plist = client.get("/api/products", headers=h).json()
    assert len(plist) == 1 and plist[0]["run_count"] == 3 and plist[0]["latest_run_id"] == third["id"] and plist[0]["location"] == "Abuja"
    p = client.get(f"/api/products/{first['product_id']}", headers=h).json()
    assert [r["run_number"] for r in p["runs"]] == [3, 2, 1] and p["runs"][2]["changes"] == [] and p["runs"][0]["persona_count"] == 3


def test_new_analysis_without_product_id_is_a_new_product(client):
    h = signup(client)
    a, b = run(client, h), run(client, h)
    assert a["product_id"] != b["product_id"] and len(client.get("/api/products", headers=h).json()) == 2


def test_rename_and_ownership(client):
    h1, h2 = signup(client), signup(client, "b@example.com")
    r = run(client, h1)
    pid = r["product_id"]
    assert client.patch(f"/api/products/{pid}", json={"name": "Zip 5 Pro"}, headers=h1).json()["name"] == "Zip 5 Pro"
    assert client.patch(f"/api/products/{pid}", json={"name": ""}, headers=h1).status_code == 422
    assert client.get(f"/api/products/{pid}", headers=h2).status_code == 404
    assert client.delete(f"/api/products/{pid}", headers=h2).status_code == 404
    assert client.post("/api/analyses", json={"intake": INTAKE, "product_id": pid}, headers=h2).status_code == 404  # cannot add runs to someone else's product
    assert client.post("/api/analyses", json={"intake": INTAKE, "product_id": "nope"}, headers=h1).status_code == 404
    assert client.post("/api/analyses", json={"intake": INTAKE, "product_id": pid, "based_on": "nope"}, headers=h1).status_code == 404
    assert client.get("/api/products", headers=h2).json() == []


def test_deleting_a_run_keeps_the_product_until_its_last_run_goes(client):
    h = signup(client)
    a = run(client, h)
    b = run(client, h, {**INTAKE, "price": 1}, product_id=a["product_id"])
    assert client.delete(f"/api/analyses/{a['id']}", headers=h).status_code == 204
    assert client.get(f"/api/products/{a['product_id']}", headers=h).json()["runs"][0]["id"] == b["id"]
    assert client.delete(f"/api/analyses/{b['id']}", headers=h).status_code == 204
    assert client.get(f"/api/products/{a['product_id']}", headers=h).status_code == 404 and client.get("/api/products", headers=h).json() == []


def test_deleting_a_product_removes_all_its_runs(client):
    h = signup(client)
    a = run(client, h)
    b = run(client, h, {**INTAKE, "price": 1}, product_id=a["product_id"])
    assert client.delete(f"/api/products/{a['product_id']}", headers=h).status_code == 204
    assert client.get(f"/api/analyses/{a['id']}", headers=h).status_code == 404 and client.get(f"/api/analyses/{b['id']}", headers=h).status_code == 404
    assert client.get("/api/analyses", headers=h).json() == []
