"""Generate 100 mock Laya Healthcare users with policies and claims."""
import json
import random
import uuid
from datetime import date, timedelta

random.seed(42)

FIRST_NAMES_M = ["Liam", "Conor", "Sean", "Patrick", "Cian", "Niall", "Eoin",
                  "Darragh", "Ronan", "Fionn", "Brian", "Declan", "Kevin", "Cathal",
                  "Oisin", "Tadhg", "Fergus", "Colm", "Donal", "Brendan"]
FIRST_NAMES_F = ["Aoife", "Ciara", "Niamh", "Siobhan", "Aisling", "Orla", "Sinead",
                  "Caoimhe", "Roisin", "Grainne", "Clodagh", "Maeve", "Sorcha", "Fiona",
                  "Laura", "Emma", "Aoibhin", "Dearbhla", "Sadhbh", "Cliona"]
LAST_NAMES = ["Murphy", "Kelly", "O'Brien", "Walsh", "Smith", "O'Connor", "McCarthy",
              "Byrne", "Ryan", "O'Sullivan", "O'Neill", "Doyle", "Lynch", "Gallagher",
              "Murray", "Doherty", "Kennedy", "Nolan", "Quinn", "Healy"]
STREETS = ["Oak Street", "Main Street", "Church Road", "Park Avenue", "Castle Drive",
           "River Lane", "High Street", "Mill Road", "Station Road", "Green Way"]
CITIES = ["Dublin", "Cork", "Galway", "Limerick", "Waterford", "Kilkenny",
          "Sligo", "Drogheda", "Tralee", "Ennis"]
POSTCODES = ["D01", "D02", "D04", "D06", "D08", "T12", "H91", "V94", "X91", "F91"]

TRAVEL_PRODUCTS = [
    "Single & Annual Multi-Trip Travel Insurance",
    "Backpacker Travel Insurance",
    "Laya Healthcare Medicare Travel Insurance",
]
CAR_HIRE_PRODUCTS = [
    "Car Hire Excess Insurance Single Trip",
    "Car Hire Excess Insurance Annual Multi-Trip",
    "Car Hire Excess Insurance Annual Multi-Trip with CDW and SLI",
]
DESTINATIONS = ["Europe", "USA", "Worldwide", "Caribbean", "Australia", "Asia", "Canada"]
CLAIM_TYPES_TRAVEL = [
    "Medical Emergency", "Trip Cancellation", "Baggage Loss",
    "Flight Delay", "Personal Accident", "Emergency Repatriation",
]
CLAIM_TYPES_CAR = [
    "Vehicle Damage", "Theft of Vehicle", "Third Party Liability", "Windscreen Damage"
]
CONDITIONS = ["None", "None", "None", "Asthma", "Diabetes Type 2",
              "Hypertension", "None", "None", "Heart Condition", "None"]


def rand_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, (end - start).days))


def fmt(d: date) -> str:
    return d.isoformat()


def policy_version(start: date) -> str:
    return "post-nov-2025" if start >= date(2025, 11, 1) else "pre-nov-2025"


def make_travel_policy(uid: str, idx: int) -> dict:
    product = random.choice(TRAVEL_PRODUCTS)
    trip_type = "single" if "Single" in product or "Backpacker" in product else "annual"
    start = rand_date(date(2025, 6, 1), date(2026, 6, 1))
    duration = random.choice([14, 21, 30, 60, 365]) if trip_type == "annual" else random.randint(7, 21)
    end = start + timedelta(days=duration if trip_type != "annual" else 365)
    excess = random.choice([0, 50, 100, 150, 200])
    premium = round(random.uniform(80, 600), 2)
    dests = random.sample(DESTINATIONS, k=random.randint(1, 2))
    status = random.choice(["active", "active", "active", "expired", "cancelled"])
    return {
        "policy_number": f"TRV-{start.year}-{100000 + idx:06d}",
        "product": product,
        "type": "travel",
        "trip_type": trip_type,
        "version": policy_version(start),
        "start_date": fmt(start),
        "end_date": fmt(end),
        "status": status,
        "excess": excess,
        "covered_destinations": dests,
        "premium_paid": premium,
    }


def make_car_policy(uid: str, idx: int) -> dict:
    product = random.choice(CAR_HIRE_PRODUCTS)
    trip_type = "annual" if "Annual" in product else "single"
    start = rand_date(date(2025, 6, 1), date(2026, 6, 1))
    end = start + timedelta(days=365 if trip_type == "annual" else random.randint(7, 21))
    excess = random.choice([500, 750, 1000, 1500])
    premium = round(random.uniform(40, 200), 2)
    status = random.choice(["active", "active", "expired"])
    return {
        "policy_number": f"CHE-{start.year}-{200000 + idx:06d}",
        "product": product,
        "type": "car_hire",
        "trip_type": trip_type,
        "version": policy_version(start),
        "start_date": fmt(start),
        "end_date": fmt(end),
        "status": status,
        "excess": excess,
        "covered_destinations": [random.choice(DESTINATIONS)],
        "premium_paid": premium,
    }


def make_claim(policy: dict, claim_idx: int) -> dict:
    is_car = policy["type"] == "car_hire"
    claim_types = CLAIM_TYPES_CAR if is_car else CLAIM_TYPES_TRAVEL
    claim_date = rand_date(
        date.fromisoformat(policy["start_date"]),
        min(date.fromisoformat(policy["end_date"]), date(2026, 7, 25)),
    )
    amount_claimed = round(random.uniform(200, 5000), 2)
    status = random.choice(["settled", "settled", "pending", "rejected"])
    amount_paid = (
        round(amount_claimed * random.uniform(0.6, 1.0), 2) if status == "settled"
        else 0.0
    )
    return {
        "claim_id": f"CLM-{claim_date.year}-{claim_idx:05d}",
        "policy_number": policy["policy_number"],
        "date": fmt(claim_date),
        "type": random.choice(claim_types),
        "amount_claimed": amount_claimed,
        "amount_paid": amount_paid,
        "status": status,
        "description": f"{random.choice(claim_types)} during trip to {random.choice(DESTINATIONS)}.",
    }


def generate_user(idx: int) -> dict:
    gender = random.choice(["M", "F"])
    first = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
    last = random.choice(LAST_NAMES)
    dob = rand_date(date(1960, 1, 1), date(2003, 12, 31))
    age = (date(2026, 7, 26) - dob).days // 365
    city = random.choice(CITIES)
    postcode = random.choice(POSTCODES)
    uid = f"USR{idx:03d}"

    num_policies = random.randint(1, 3)
    policies = []
    for p in range(num_policies):
        if random.random() < 0.7:
            policies.append(make_travel_policy(uid, idx * 10 + p))
        else:
            policies.append(make_car_policy(uid, idx * 10 + p))

    claims = []
    claim_counter = idx * 20
    for pol in policies:
        if random.random() < 0.4:
            num_claims = random.randint(1, 3)
            for _ in range(num_claims):
                try:
                    claims.append(make_claim(pol, claim_counter))
                    claim_counter += 1
                except Exception:
                    pass

    return {
        "id": uid,
        "name": f"{first} {last}",
        "gender": gender,
        "date_of_birth": fmt(dob),
        "age": age,
        "email": f"{first.lower()}.{last.lower().replace(chr(39), '')}@email.ie",
        "phone": f"+353 8{random.randint(1,9)} {random.randint(100,999)} {random.randint(1000,9999)}",
        "address": {
            "line1": f"{random.randint(1,200)} {random.choice(STREETS)}",
            "city": city,
            "postcode": postcode,
            "country": "Ireland",
        },
        "pre_existing_conditions": [random.choice(CONDITIONS)],
        "policies": policies,
        "claims": claims,
    }


if __name__ == "__main__":
    import os
    users = [generate_user(i + 1) for i in range(100)]
    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
    with open(out_path, "w") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)
    print(f"Generated {len(users)} users → {out_path}")
