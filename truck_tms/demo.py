"""Sample data so new users (and screenshots) have something to look at."""

from __future__ import annotations

from datetime import date, timedelta

from .database import (
    ComplianceItem,
    Database,
    Driver,
    Expense,
    Invoice,
    Load,
    Maintenance,
    Statement,
    StatementItem,
    Truck,
)
from .weeks import week_start


def seed_demo_data(db: Database) -> None:
    """Fill an empty database with trucks, drivers, loads, maintenance and statements."""
    if db.list_trucks():
        return
    today = date.today()
    last_week = week_start(today - timedelta(days=7), db.week_start_dow)
    prev_week = last_week - timedelta(days=7)

    def d(base: date, offset: int) -> str:
        return (base + timedelta(days=offset)).isoformat()

    john = db.add_driver(Driver(name="John Miller", phone="+1 312 555 0142", license_number="IL-D123-4567",
                                license_expiry=d(today, 400), pay_type="percent", pay_rate=30))
    maria = db.add_driver(Driver(name="Maria Lopez", phone="+1 214 555 0199", license_number="TX-88765432",
                                 license_expiry=d(today, 25), pay_type="per_mile", pay_rate=0.65))
    db.add_driver(Driver(name="Ahmet Yılmaz", phone="+1 773 555 0110", pay_type="weekly", pay_rate=1500))

    t1 = db.add_truck(Truck(plate="P123456", unit_number="101", make="Freightliner", model="Cascadia",
                            year=2022, vin="1FUJHHDR0NLNA1234", odometer=412_350, owner_name="Eagle Owner LLC",
                            driver_id=john, dispatch_fee_percent=10))
    t2 = db.add_truck(Truck(unit_number="102", make="Kenworth", model="T680", year=2021, odometer=538_900,
                            owner_name="Lone Star Trucking Inc", driver_id=maria, dispatch_fee_percent=8))
    t3 = db.add_truck(Truck(plate="XYZ7788", make="Peterbilt", model="579", year=2019, odometer=701_220,
                            status="maintenance"))
    db.change_plate(t1, "P654321")

    loads = [
        # last week — truck 101 / John
        Load(truck_id=t1, driver_id=john, load_number="4410021", broker="Acme Logistics",
             pickup_location="Chicago, IL", pickup_date=d(last_week, 0), delivery_location="Dallas, TX",
             delivery_date=d(last_week, 1), rate=2850, loaded_miles=925, dead_miles=40,
             commodity="Paper goods", status="paid"),
        Load(truck_id=t1, driver_id=john, load_number="4410055", broker="Blue Freight",
             pickup_location="Dallas, TX", pickup_date=d(last_week, 2), delivery_location="Atlanta, GA",
             delivery_date=d(last_week, 3), rate=2400, extra_pay=150, loaded_miles=780, dead_miles=35,
             notes="Detention 3h", status="invoiced"),
        Load(truck_id=t1, driver_id=john, load_number="4410090", broker="Peach Brokers",
             pickup_location="Atlanta, GA", pickup_date=d(last_week, 4), rate=250, is_tonu=True,
             status="cancelled", notes="Shipper cancelled on arrival"),
        Load(truck_id=t1, driver_id=john, load_number="4410102", broker="Blue Freight",
             pickup_location="Atlanta, GA", pickup_date=d(last_week, 5), delivery_location="Columbus, OH",
             delivery_date=d(last_week, 6), rate=1750, loaded_miles=570, dead_miles=60, status="delivered"),
        # last week — truck 102 / Maria
        Load(truck_id=t2, driver_id=maria, load_number="7781001", broker="Acme Logistics",
             pickup_location="Denver, CO", pickup_date=d(last_week, 1), delivery_location="Phoenix, AZ",
             delivery_date=d(last_week, 2), rate=2100, loaded_miles=820, dead_miles=25, status="delivered"),
        Load(truck_id=t2, driver_id=maria, load_number="7781002", broker="Desert Haul",
             pickup_location="Phoenix, AZ", pickup_date=d(last_week, 3), delivery_location="Los Angeles, CA",
             delivery_date=d(last_week, 4), rate=1650, loaded_miles=372, dead_miles=18, status="delivered"),
        # previous week — truck 101
        Load(truck_id=t1, driver_id=john, load_number="4409870", broker="Acme Logistics",
             pickup_location="Indianapolis, IN", pickup_date=d(prev_week, 1), delivery_location="Chicago, IL",
             delivery_date=d(prev_week, 2), rate=1100, loaded_miles=183, dead_miles=20, status="paid"),
        # this week / not delivered yet
        Load(truck_id=t1, driver_id=john, load_number="4410150", broker="Blue Freight",
             pickup_location="Columbus, OH", pickup_date=today.isoformat(), delivery_location="Newark, NJ",
             status="in_transit", rate=1900, loaded_miles=530, dead_miles=15),
        Load(load_number="9900001", pickup_location="Memphis, TN", status="planned"),
    ]
    for load in loads:
        load.id = db.add_load(load)
    by_number = {load.load_number.lstrip("#"): load for load in loads if load.load_number}

    # a few weeks of paid history so the overview charts have something to show
    brokers = ["Acme Logistics", "Blue Freight", "Desert Haul", "Great Lakes Freight", "Lone Star Brokerage",
               "Peach Brokers"]
    cities = ["Chicago, IL", "Dallas, TX", "Atlanta, GA", "Denver, CO", "Phoenix, AZ", "Memphis, TN",
              "Columbus, OH", "Kansas City, MO", "Nashville, TN", "Houston, TX"]
    history: list[int] = []
    for weeks_back in range(3, 9):  # older than the demo statements, so their totals stay as they are
        base = last_week - timedelta(days=7 * (weeks_back - 1))
        for truck_id, driver_id, offset in ((t1, john, 0), (t2, maria, 5)):
            for k in range(2):
                seed = weeks_back * 10 + k + offset
                loaded = 420 + (seed * 37) % 520
                rate = round(loaded * (2.3 + ((seed * 13) % 95) / 100), -1)
                history.append(db.add_load(Load(
                    truck_id=truck_id, driver_id=driver_id, load_number=str(7_700_000 + seed * 7),
                    broker=brokers[seed % len(brokers)],
                    pickup_location=cities[seed % len(cities)], pickup_date=d(base, k * 3),
                    delivery_location=cities[(seed + 3) % len(cities)], delivery_date=d(base, k * 3 + 1),
                    rate=rate, loaded_miles=loaded, dead_miles=20 + (seed * 7) % 60, status="paid")))
                # rough miles by state for IFTA: half in the pickup state, half in the delivery state
                start, end = cities[seed % len(cities)][-2:], cities[(seed + 3) % len(cities)][-2:]
                total = db.get_load(history[-1]).total_miles
                db.set_load_states(history[-1], [(start, round(total / 2)), (end, total - round(total / 2))])
                gallons = round(total / (6.2 + (seed % 7) / 10), 1)  # about 6.5 MPG
                db.add_expense(Expense(truck_id=truck_id, date=d(base, k * 3), category="fuel",
                                       amount=round(gallons * 3.85, 2), gallons=gallons, state=start,
                                       description="Fuel card"))

    for m in [
        Maintenance(truck_id=t1, date=d(prev_week, 3), service_type="pm_service", odometer=410_100, cost=485,
                    vendor="TA Truck Service", description="PM-A: oil, filters, grease",
                    next_due_odometer=435_100, next_due_date=d(today, 80)),
        Maintenance(truck_id=t2, date=d(today, -120), service_type="oil_change", odometer=512_000, cost=390,
                    vendor="Speedco", next_due_odometer=537_000),
        Maintenance(truck_id=t3, date=d(today, -2), service_type="brakes", odometer=701_220, cost=1840,
                    vendor="Rush Truck Center", description="Drive axle brake shoes + drums"),
    ]:
        db.add_maintenance(m)

    db.add_expense(Expense(truck_id=t1, date=d(last_week, 2), category="insurance", amount=410))

    db.save_statement(
        Statement(truck_id=t1, week_start=last_week.isoformat(), fuel_amount=1435.60, fuel_gallons=362.4,
                  tolls=86.25, dispatch_fee_percent=10, driver_paid_amount=2000,
                  driver_paid_date=d(today, -1), status="final"),
        [
            StatementItem(kind="driver_addition", description="Detention share", amount=50),
            StatementItem(kind="driver_deduction", description="Cash advance", amount=200),
            StatementItem(kind="owner_deduction", description="Trailer rental", amount=275),
            StatementItem(kind="owner_deduction", description="Insurance", amount=410),
        ],
    )
    db.save_statement(
        Statement(truck_id=t2, week_start=last_week.isoformat(), fuel_amount=780, fuel_gallons=198,
                  tolls=0, dispatch_fee_percent=8, status="draft"),
        [StatementItem(kind="owner_deduction", description="ELD subscription", amount=35)],
    )
    db.save_statement(
        Statement(truck_id=t1, week_start=prev_week.isoformat(), fuel_amount=260, fuel_gallons=66,
                  dispatch_fee_percent=10, driver_paid_amount=330, driver_paid_date=d(prev_week, 9),
                  status="paid"),
        [],
    )
    _seed_billing_and_compliance(db, today, last_week, by_number, history, (john, maria), (t1, t2))


def _seed_billing_and_compliance(db: Database, today: date, last_week: date, loads: dict[str, Load],
                                 history: list[int], drivers: tuple[int, int], trucks: tuple[int, int]) -> None:
    """Invoices, expiring documents, miles by state and fuel purchases for the v0.6 pages."""
    def d(base: date, offset: int) -> str:
        return (base + timedelta(days=offset)).isoformat()

    john, maria = drivers
    t1, t2 = trucks
    # miles by state (loaded + empty), so the IFTA page has a quarter to show
    for number, states in {
        "4410021": [("IL", 290), ("MO", 290), ("OK", 235), ("TX", 150)],
        "4410055": [("TX", 200), ("LA", 210), ("MS", 170), ("AL", 160), ("GA", 75)],
        "4410102": [("GA", 120), ("TN", 200), ("KY", 190), ("OH", 120)],
        "7781001": [("CO", 300), ("NM", 380), ("AZ", 165)],
        "7781002": [("AZ", 150), ("CA", 240)],
        "4410150": [("OH", 180), ("PA", 310), ("NJ", 55)],
        "4409870": [("IN", 135), ("IL", 68)],
    }.items():
        db.set_load_states(loads[number].id, states)
    for truck, day, state, gallons, price in (
        (t1, 0, "IL", 120.5, 4.19), (t1, 2, "TX", 140.2, 3.69), (t1, 4, "GA", 101.7, 3.79),
        (t2, 1, "CO", 95.4, 3.99), (t2, 3, "AZ", 102.6, 4.29),
    ):
        db.add_expense(Expense(truck_id=truck, date=d(last_week, day), category="fuel",
                               amount=round(gallons * price, 2), gallons=gallons, state=state,
                               description="Fuel card"))
    for truck, days_ago, category, amount, note in (
        (t1, 12, "tolls", 312.40, "E-ZPass"), (t2, 33, "repair", 1280.00, "Turbo hose + labor"),
        (t1, 47, "permits", 180.00, "Oversize permit"), (t2, 20, "tolls", 96.75, "PrePass"),
        (t1, 64, "maintenance", 640.00, "Tires rotated + alignment"),
    ):
        db.add_expense(Expense(truck_id=truck, date=d(today, -days_ago), category=category, amount=amount,
                               description=note))
    # sample rates per gallon (enter the real ones of your quarter from iftach.org)
    db.set_ifta_rates({"IL": 0.70, "MO": 0.32, "OK": 0.19, "TX": 0.20, "LA": 0.20, "MS": 0.18, "AL": 0.31,
                       "GA": 0.37, "TN": 0.27, "KY": 0.29, "OH": 0.47, "CO": 0.33, "NM": 0.21, "AZ": 0.26,
                       "CA": 0.97, "IN": 0.59, "PA": 0.74, "NJ": 0.53})

    # invoices: paid, open, factored and one that is late
    db.add_invoice(Invoice(invoice_number=db.next_invoice_number(), load_id=loads["4410021"].id,
                           issue_date=d(last_week, 1), amount=2850, bill_to="Acme Logistics\nChicago, IL",
                           paid_amount=2850, paid_date=d(today, -2)))
    db.add_invoice(Invoice(invoice_number=db.next_invoice_number(), load_id=loads["4410055"].id,
                           issue_date=d(last_week, 3), amount=2550, bill_to="Blue Freight\nDallas, TX"))
    db.add_invoice(Invoice(invoice_number=db.next_invoice_number(), load_id=loads["7781001"].id,
                           issue_date=d(last_week, 2), amount=2100, terms_days=0, method="factoring",
                           fee=63, paid_amount=2037, paid_date=d(last_week, 3), bill_to="Acme Logistics"))
    late = db.get_load(history[-1])
    db.add_invoice(Invoice(invoice_number=db.next_invoice_number(), load_id=late.id, issue_date=late.delivery_date,
                           amount=late.gross, bill_to=late.broker))
    if len(history) > 3:
        older = db.get_load(history[-3])
        db.add_invoice(Invoice(invoice_number=db.next_invoice_number(), load_id=older.id,
                               issue_date=older.delivery_date, amount=older.gross, bill_to=older.broker,
                               paid_amount=round(older.gross / 2, 2), paid_date=d(today, -10)))

    # documents and filings that expire
    for item in (
        ComplianceItem(kind="medical_card", expiry_date=d(today, 18), driver_id=john, reference="MEC-55821"),
        ComplianceItem(kind="medical_card", expiry_date=d(today, 410), driver_id=maria),
        ComplianceItem(kind="drug_test", expiry_date=d(today, 160), driver_id=john),
        ComplianceItem(kind="registration", expiry_date=d(today, 210), truck_id=t1, reference="IRP 2026-0441"),
        ComplianceItem(kind="insurance", expiry_date=d(today, 95), truck_id=t1, reference="POL-778812"),
        ComplianceItem(kind="annual_inspection", expiry_date=d(today, -4), truck_id=t2),
        ComplianceItem(kind="registration", expiry_date=d(today, 300), truck_id=t2),
        ComplianceItem(kind="ucr", expiry_date=d(today, 41)),
        ComplianceItem(kind="form_2290", expiry_date=d(today, 250)),
    ):
        db.add_compliance(item)
