"""Sample data so new users (and screenshots) have something to look at."""

from __future__ import annotations

from datetime import date, timedelta

from .database import Database, Driver, Expense, Load, Maintenance, Statement, StatementItem, Truck
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
        db.add_load(load)

    # a few weeks of paid history so the overview charts have something to show
    brokers = ["Acme Logistics", "Blue Freight", "Desert Haul", "Great Lakes Freight", "Lone Star Brokerage",
               "Peach Brokers"]
    cities = ["Chicago, IL", "Dallas, TX", "Atlanta, GA", "Denver, CO", "Phoenix, AZ", "Memphis, TN",
              "Columbus, OH", "Kansas City, MO", "Nashville, TN", "Houston, TX"]
    for weeks_back in range(3, 9):  # older than the demo statements, so their totals stay as they are
        base = last_week - timedelta(days=7 * (weeks_back - 1))
        for truck_id, driver_id, offset in ((t1, john, 0), (t2, maria, 5)):
            for k in range(2):
                seed = weeks_back * 10 + k + offset
                loaded = 420 + (seed * 37) % 520
                rate = round(loaded * (2.3 + ((seed * 13) % 95) / 100), -1)
                db.add_load(Load(
                    truck_id=truck_id, driver_id=driver_id, load_number=str(7_700_000 + seed * 7),
                    broker=brokers[seed % len(brokers)],
                    pickup_location=cities[seed % len(cities)], pickup_date=d(base, k * 3),
                    delivery_location=cities[(seed + 3) % len(cities)], delivery_date=d(base, k * 3 + 1),
                    rate=rate, loaded_miles=loaded, dead_miles=20 + (seed * 7) % 60, status="paid"))

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
