"""Load the audit summaries and the commerce aggregates behind the dashboard."""

import json
from pathlib import Path

import pandas as pd

OUTPUT_NAMES = (
    "delivery_status_summary.csv",
    "state_performance.csv",
    "region_performance.csv",
    "review_by_status.csv",
    "review_by_delay_bin.csv",
    "category_performance.csv",
)

MONTH_START = "2017-01"
MONTH_END = "2018-08"


def load_state_centers(data_dir: Path) -> pd.DataFrame:
    """One map point per state, from the geolocation file."""
    geo = pd.read_csv(
        data_dir / "olist_geolocation_dataset.csv",
        usecols=["geolocation_lat", "geolocation_lng", "geolocation_state"],
    )
    geo = geo.loc[
        geo["geolocation_lat"].between(-34, 6) & geo["geolocation_lng"].between(-74, -32)
    ]
    return (
        geo.groupby("geolocation_state", as_index=False)
        .agg(lat=("geolocation_lat", "median"), lng=("geolocation_lng", "median"))
        .rename(columns={"geolocation_state": "customer_state"})
    )


def load_summaries(output_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [name for name in OUTPUT_NAMES if not (output_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Missing audit tables: " + ", ".join(missing))
    return {name.removesuffix(".csv"): pd.read_csv(output_dir / name) for name in OUTPUT_NAMES}


def _as_late_flag(values: pd.Series) -> pd.Series:
    return values.map({"true": True, "false": False, True: True, False: False})


def _load_saved_commerce(output_dir: Path) -> dict:
    """Dashboard tables built from the raw files and stored without those files."""
    names = (
        "commerce_frame.csv",
        "commerce_items.csv",
        "commerce_payments.csv",
        "commerce_stages.csv",
        "commerce_monthly.csv",
    )
    missing = [name for name in names if not (output_dir / name).exists()]
    if missing:
        raise FileNotFoundError("Missing commerce tables: " + ", ".join(missing))
    frame = pd.read_csv(output_dir / "commerce_frame.csv")
    frame["is_late"] = _as_late_flag(frame["is_late"])
    items = pd.read_csv(output_dir / "commerce_items.csv")
    payments = pd.read_csv(output_dir / "commerce_payments.csv")
    stages = pd.read_csv(output_dir / "commerce_stages.csv")
    monthly = pd.read_csv(output_dir / "commerce_monthly.csv")
    delivered = frame.loc[frame["is_late"].notna()]
    reviewed = delivered.loc[delivered["review_score"].notna()]
    negatives = reviewed.loc[reviewed["review_score"] <= 2]
    orders_per_customer = frame.groupby("customer_unique_id").size()
    return {
        "revenue": float(items["price"].sum()),
        "orders": int(frame["order_id"].nunique()),
        "customers": int(frame["customer_unique_id"].nunique()),
        "aov": float(frame["price"].mean()),
        "avg_review": float(frame["review_score"].mean()),
        "avg_delivery_days": float(delivered["actual_days"].mean()),
        "late_rate": float(delivered["is_late"].mean()),
        "repeat_rate": float((orders_per_customer > 1).mean()),
        "negative_rate": float((reviewed["review_score"] <= 2).mean()) if len(reviewed) else float("nan"),
        "negative_rate_late": float(reviewed.loc[reviewed["is_late"] == True, "review_score"].le(2).mean()) if len(reviewed) else float("nan"),
        "negative_rate_ontime": float(reviewed.loc[reviewed["is_late"] == False, "review_score"].le(2).mean()) if len(reviewed) else float("nan"),
        "negative_from_ontime": float((negatives["is_late"] == False).mean()) if len(negatives) else float("nan"),
        "monthly": monthly,
        "categories": items.groupby("category", as_index=False)["price"].sum().sort_values("price", ascending=False).head(8),
        "score_dist": frame["review_score"].dropna().value_counts().sort_index().rename_axis("score").reset_index(name="reviews"),
        "state_orders": frame.groupby("customer_state", as_index=False).size().rename(columns={"size": "orders"}).sort_values("orders", ascending=False),
        "payments": payments["payment_type"].value_counts().rename_axis("payment_type").reset_index(name="records"),
        "payment_rows": payments,
        "item_rows": items,
        "frame": frame,
        "stages": stages,
    }


def load_commerce(data_dir: Path, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or data_dir.parent / "outputs"
    if not (data_dir / "olist_orders_dataset.csv").exists():
        return _load_saved_commerce(output_dir)
    orders = pd.read_csv(
        data_dir / "olist_orders_dataset.csv",
        usecols=[
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        parse_dates=[
            "order_purchase_timestamp",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
    )
    customers = pd.read_csv(
        data_dir / "olist_customers_dataset.csv",
        usecols=["customer_id", "customer_unique_id", "customer_state"],
    )
    reviews = pd.read_csv(
        data_dir / "olist_order_reviews_dataset.csv",
        usecols=["order_id", "review_score"],
    )
    items = pd.read_csv(
        data_dir / "olist_order_items_dataset.csv",
        usecols=["order_id", "product_id", "price"],
    )
    products = pd.read_csv(
        data_dir / "olist_products_dataset.csv",
        usecols=["product_id", "product_category_name"],
    )
    translation = pd.read_csv(data_dir / "product_category_name_translation.csv")
    payments = pd.read_csv(
        data_dir / "olist_order_payments_dataset.csv",
        usecols=["order_id", "payment_type"],
    )

    orders["month"] = orders["order_purchase_timestamp"].dt.to_period("M").astype(str)
    order_value = items.groupby("order_id", as_index=False)["price"].sum()

    delivered = orders.loc[
        (orders["order_status"] == "delivered")
        & orders["order_delivered_customer_date"].notna()
        & orders["order_estimated_delivery_date"].notna()
    ].copy()
    delivered["days_difference"] = (
        delivered["order_estimated_delivery_date"].dt.normalize()
        - delivered["order_delivered_customer_date"].dt.normalize()
    ).dt.days
    delivered["actual_days"] = (
        delivered["order_delivered_customer_date"].dt.normalize()
        - delivered["order_purchase_timestamp"].dt.normalize()
    ).dt.days
    delivered["is_late"] = delivered["days_difference"] < 0

    with_carrier = delivered.loc[delivered["order_delivered_carrier_date"].notna()].copy()
    with_carrier["handling_days"] = (
        with_carrier["order_delivered_carrier_date"].dt.normalize()
        - with_carrier["order_purchase_timestamp"].dt.normalize()
    ).dt.days
    with_carrier["transit_days"] = (
        with_carrier["order_delivered_customer_date"].dt.normalize()
        - with_carrier["order_delivered_carrier_date"].dt.normalize()
    ).dt.days

    review_one = reviews.groupby("order_id", as_index=False)["review_score"].mean()
    reviewed = delivered.merge(review_one, on="order_id", how="inner")
    reviewed["is_negative"] = reviewed["review_score"] <= 2

    stages = (
        with_carrier.groupby("is_late", as_index=False)
        .agg(handling_days=("handling_days", "mean"), transit_days=("transit_days", "mean"))
    )
    stages["group"] = stages["is_late"].map({False: "On time", True: "Late"})

    late_by_month = delivered.groupby("month", as_index=False)["is_late"].mean()
    neg_by_month = reviewed.groupby("month", as_index=False)["is_negative"].mean()
    revenue_by_month = (
        items.merge(orders[["order_id", "month"]], on="order_id", how="left")
        .groupby("month", as_index=False)["price"]
        .sum()
    )
    orders_by_month = orders.groupby("month", as_index=False).size()
    monthly = (
        orders_by_month.merge(revenue_by_month, on="month", how="left")
        .merge(late_by_month, on="month", how="left")
        .merge(neg_by_month, on="month", how="left")
        .rename(columns={"size": "orders", "price": "revenue", "is_late": "late_rate", "is_negative": "negative_share"})
    )
    monthly = monthly.loc[monthly["month"].between(MONTH_START, MONTH_END)].reset_index(drop=True)

    catalog = products.merge(translation, on="product_category_name", how="left")
    item_categories = items.merge(catalog[["product_id", "product_category_name_english"]], on="product_id", how="left")
    item_categories["category"] = item_categories["product_category_name_english"].fillna("unknown")
    categories = (
        item_categories.groupby("category", as_index=False)["price"]
        .sum()
        .sort_values("price", ascending=False)
        .head(8)
    )

    score_dist = (
        reviews["review_score"]
        .value_counts()
        .sort_index()
        .rename_axis("score")
        .reset_index(name="reviews")
    )
    state_orders = (
        orders.merge(customers[["customer_id", "customer_state"]], on="customer_id", how="left")
        .groupby("customer_state", as_index=False)
        .size()
        .rename(columns={"size": "orders"})
        .sort_values("orders", ascending=False)
    )
    pay = payments.loc[payments["payment_type"] != "not_defined", "payment_type"]
    payment_share = pay.value_counts().rename_axis("payment_type").reset_index(name="records")
    payment_rows = payments.loc[payments["payment_type"] != "not_defined", ["order_id", "payment_type"]]

    primary = (
        item_categories.sort_values(["order_id", "price"], ascending=[True, False])
        .drop_duplicates("order_id")[["order_id", "category"]]
    )
    frame = orders.merge(
        customers[["customer_id", "customer_unique_id", "customer_state"]],
        on="customer_id",
        how="left",
    )
    frame["region"] = frame["customer_state"].map(REGION).fillna("Other")
    frame["year"] = frame["order_purchase_timestamp"].dt.year.astype(int)
    frame = frame.merge(order_value, on="order_id", how="left")
    frame["price"] = frame["price"].fillna(0.0)
    frame = frame.merge(delivered[["order_id", "is_late", "actual_days"]], on="order_id", how="left")
    frame = frame.merge(review_one, on="order_id", how="left")
    frame = frame.merge(primary, on="order_id", how="left")
    frame = frame[
        [
            "order_id",
            "month",
            "year",
            "region",
            "customer_state",
            "customer_unique_id",
            "price",
            "is_late",
            "actual_days",
            "review_score",
            "category",
        ]
    ]
    item_rows = item_categories[["order_id", "category", "price"]]

    orders_per_customer = customers.groupby("customer_unique_id").size()
    negatives = reviewed.loc[reviewed["is_negative"]]

    return {
        "revenue": float(items["price"].sum()),
        "orders": int(orders["order_id"].nunique()),
        "customers": int(customers["customer_unique_id"].nunique()),
        "aov": float(order_value["price"].mean()),
        "avg_review": float(reviews["review_score"].mean()),
        "avg_delivery_days": float(delivered["actual_days"].mean()),
        "late_rate": float(delivered["is_late"].mean()),
        "repeat_rate": float((orders_per_customer > 1).mean()),
        "negative_rate": float(reviewed["is_negative"].mean()),
        "negative_rate_late": float(reviewed.loc[reviewed["is_late"], "is_negative"].mean()),
        "negative_rate_ontime": float(reviewed.loc[~reviewed["is_late"], "is_negative"].mean()),
        "negative_from_ontime": float((~negatives["is_late"]).mean()),
        "monthly": monthly,
        "categories": categories,
        "score_dist": score_dist,
        "state_orders": state_orders,
        "payments": payment_share,
        "payment_rows": payment_rows,
        "item_rows": item_rows,
        "frame": frame,
        "stages": stages,
    }


REGION = {
    "SP": "Southeast", "RJ": "Southeast", "MG": "Southeast", "ES": "Southeast",
    "PR": "South", "SC": "South", "RS": "South",
    "DF": "Central-West", "GO": "Central-West", "MT": "Central-West", "MS": "Central-West",
    "BA": "Northeast", "CE": "Northeast", "PE": "Northeast", "MA": "Northeast",
    "PB": "Northeast", "RN": "Northeast", "AL": "Northeast", "PI": "Northeast", "SE": "Northeast",
    "PA": "North", "AM": "North", "RO": "North", "AC": "North", "RR": "North", "AP": "North", "TO": "North",
}
REGION_ORDER = ["Southeast", "South", "Central-West", "Northeast", "North"]
DASHBOARD_REGIONS = ["All regions", *REGION_ORDER]
DASHBOARD_YEARS = ["All years", "2016", "2017", "2018"]
DASHBOARD_DELIVERIES = ["All orders", "On time", "Late"]


def _clean_number(value):
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (bytes, str)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    try:
        if pd.isna(value):
            return None
    except TypeError:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return float(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    rows = frame.to_dict(orient="records")
    return [{key: _clean_number(value) if not isinstance(value, str) else value for key, value in row.items()} for row in rows]


def dashboard_slice(frame: pd.DataFrame, item_rows: pd.DataFrame, payment_rows: pd.DataFrame, region: str, year: str, delivery: str) -> dict:
    """One dashboard selection, as totals and small tables. No order rows."""
    scoped = frame
    if region != "All regions":
        scoped = scoped.loc[scoped["region"] == region]
    if year != "All years":
        scoped = scoped.loc[scoped["year"] == int(year)]
    view = scoped
    if delivery == "On time":
        view = view.loc[view["is_late"] == False]
    elif delivery == "Late":
        view = view.loc[view["is_late"] == True]
    if view.empty:
        return {"empty": True}

    reviewed = view.loc[view["review_score"].notna()]
    scope_delivered = scoped.loc[scoped["is_late"].notna()]
    scope_late = float(scope_delivered["is_late"].mean()) if not scope_delivered.empty else float("nan")
    on_time = view.loc[view["is_late"] == False, "review_score"]
    late = view.loc[view["is_late"] == True, "review_score"]
    on_time_score = float(on_time.mean()) if on_time.notna().any() else float("nan")
    late_score = float(late.mean()) if late.notna().any() else float("nan")
    repeat_customers = view.groupby("customer_unique_id").size()
    repeat_rate = float((repeat_customers > 1).mean()) if not repeat_customers.empty else float("nan")
    avg_delivery = float(view["actual_days"].mean()) if view["actual_days"].notna().any() else float("nan")
    avg_review = float(reviewed["review_score"].mean()) if not reviewed.empty else float("nan")

    regions = (
        view.groupby("region", as_index=False)
        .agg(revenue=("price", "sum"), orders=("order_id", "nunique"))
        .merge(
            scope_delivered.groupby("region", as_index=False).agg(
                delivered=("order_id", "size"),
                late_rate=("is_late", "mean"),
            ),
            on="region",
            how="outer",
        )
    )
    regions = regions.loc[regions["region"].isin(REGION_ORDER)].copy()
    regions["revenue"] = regions["revenue"].fillna(0.0)

    states = (
        scope_delivered.groupby("customer_state", as_index=False)
        .agg(delivered=("order_id", "size"), late_rate=("is_late", "mean"))
        .sort_values("delivered", ascending=False)
        .head(8)
        .sort_values("delivered", ascending=True)
    )
    promise = [
        {"name": "On time", "value": float(view.loc[view["is_late"] == False, "price"].sum()), "count": int((view["is_late"] == False).sum())},
        {"name": "Late", "value": float(view.loc[view["is_late"] == True, "price"].sum()), "count": int((view["is_late"] == True).sum())},
        {"name": "No arrival", "value": float(view.loc[view["is_late"].isna(), "price"].sum()), "count": int(view["is_late"].isna().sum())},
    ]
    by_year = (
        view.groupby("year", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("price", "sum"))
        .sort_values("year")
    )
    trip = (
        scope_delivered.groupby("region", as_index=False)
        .agg(days=("actual_days", "mean"), delivered=("order_id", "size"))
        .dropna(subset=["days"])
        .sort_values("days", ascending=False)
    )
    star_region = (
        scoped.loc[scoped["review_score"].notna()]
        .groupby("region", as_index=False)
        .agg(score=("review_score", "mean"), reviews=("order_id", "size"))
        .sort_values("score", ascending=True)
    )
    scored = scoped.loc[scoped["review_score"].notna()].copy()
    if scored.empty:
        weak = scored
        weak_line = float("nan")
    else:
        scored["weak"] = scored["review_score"] <= 2
        weak = (
            scored.groupby("region", as_index=False)
            .agg(weak_rate=("weak", "mean"), reviews=("order_id", "size"))
            .sort_values("weak_rate", ascending=False)
        )
        weak_line = float(scored["weak"].mean())
    monthly = (
        view.groupby("month", as_index=False)
        .agg(orders=("order_id", "nunique"), revenue=("price", "sum"))
        .sort_values("month")
    )
    if year == "All years":
        monthly = monthly.loc[monthly["month"].between(MONTH_START, MONTH_END)]
    month_base = scope_delivered.groupby("month", as_index=False)["is_late"].mean()
    month_neg = scoped.loc[scoped["review_score"].notna()].copy()
    if month_neg.empty:
        trend = month_neg
    else:
        month_neg["is_negative"] = month_neg["review_score"] <= 2
        month_neg = month_neg.groupby("month", as_index=False)["is_negative"].mean()
        trend = month_base.merge(month_neg, on="month", how="inner").sort_values("month")
        if year == "All years":
            trend = trend.loc[trend["month"].between(MONTH_START, MONTH_END)]
    cats = (
        item_rows.loc[item_rows["order_id"].isin(view["order_id"])]
        .groupby("category", as_index=False)["price"]
        .sum()
        .sort_values("price", ascending=False)
        .head(8)
        .sort_values("price", ascending=True)
    )
    typed = scoped.loc[scoped["is_late"].notna() & scoped["category"].notna()]
    focus = (
        typed.groupby("category", as_index=False)
        .agg(delivered_orders=("order_id", "size"), late_rate=("is_late", "mean"), avg_review_score=("review_score", "mean"))
        .loc[lambda rows: rows["delivered_orders"] >= 100]
        .sort_values("late_rate", ascending=False)
        .head(8)
        .sort_values("late_rate", ascending=True)
    )
    if reviewed.empty:
        dist = pd.DataFrame(columns=["score", "reviews"])
    else:
        dist = (
            reviewed["review_score"].round().clip(1, 5).value_counts().sort_index()
            .rename_axis("score").reset_index(name="reviews")
        )
    pays = (
        payment_rows.loc[payment_rows["order_id"].isin(view["order_id"]), "payment_type"]
        .value_counts()
        .rename_axis("payment_type")
        .reset_index(name="records")
    )
    pay_late = payment_rows.merge(scope_delivered[["order_id", "is_late"]], on="order_id", how="inner")
    pay_rate = (
        pay_late.groupby("payment_type", as_index=False)
        .agg(records=("order_id", "size"), late_rate=("is_late", "mean"))
        .sort_values("records", ascending=False)
    )
    return {
        "empty": False,
        "revenue": float(view["price"].sum()),
        "orders": int(view["order_id"].nunique()),
        "customers": int(view["customer_unique_id"].nunique()),
        "aov": float(view["price"].mean()),
        "avg_review": avg_review,
        "avg_delivery": avg_delivery,
        "scope_late": scope_late,
        "repeat_rate": repeat_rate,
        "on_time_score": on_time_score,
        "late_score": late_score,
        "regions": regions,
        "states": states,
        "promise": promise,
        "by_year": by_year,
        "trip": trip,
        "star_region": star_region,
        "weak_line": weak_line,
        "weak": weak,
        "monthly": monthly,
        "trend": trend,
        "cats": cats,
        "focus": focus,
        "dist": dist,
        "pays": pays,
        "pay_rate": pay_rate,
    }


def _freeze_slice(pack: dict) -> dict:
    frozen = {"empty": True} if pack.get("empty") else {"empty": False}
    if pack.get("empty"):
        return frozen
    for key, value in pack.items():
        if key == "empty":
            continue
        if isinstance(value, pd.DataFrame):
            frozen[key] = _records(value)
        elif isinstance(value, list):
            frozen[key] = _records(pd.DataFrame(value)) if value and isinstance(value[0], dict) else value
        else:
            frozen[key] = _clean_number(value)
    return frozen


def _thaw_number(value):
    if value is None:
        return float("nan")
    return value


def thaw_dashboard_slice(raw: dict) -> dict:
    if raw.get("empty"):
        return {"empty": True}
    frames = {
        "regions", "states", "by_year", "trip", "star_region", "weak",
        "monthly", "trend", "cats", "focus", "dist", "pays", "pay_rate",
    }
    pack = {"empty": False, "promise": raw.get("promise") or []}
    for key, value in raw.items():
        if key in {"empty", "promise"}:
            continue
        if key in frames:
            pack[key] = pd.DataFrame(value or [])
        else:
            pack[key] = _thaw_number(value)
    return pack


def save_dashboard_public(commerce: dict, output_dir: Path) -> Path:
    """Write every filter combination as totals, without an order row."""
    slices = {}
    for region in DASHBOARD_REGIONS:
        for year in DASHBOARD_YEARS:
            for delivery in DASHBOARD_DELIVERIES:
                key = f"{region}|{year}|{delivery}"
                slices[key] = _freeze_slice(dashboard_slice(
                    commerce["frame"], commerce["item_rows"], commerce["payment_rows"], region, year, delivery,
                ))
    path = output_dir / "dashboard_public.json"
    path.write_text(json.dumps({"slices": slices}, ensure_ascii=True), encoding="utf-8")
    return path


def load_dashboard_public(output_dir: Path) -> dict:
    path = output_dir / "dashboard_public.json"
    if not path.exists():
        raise FileNotFoundError("Missing dashboard summary: dashboard_public.json")
    return json.loads(path.read_text(encoding="utf-8"))["slices"]


def load_late_risk(data_dir: Path, output_dir: Path | None = None) -> dict:
    """Score miss risk from facts known when the order is placed.

    A sales forecast does not fit: the file ends in 2018 and the decision is
    about a single order's promised date. Region and promised lead time are
    both known at purchase. Later orders (2018) are held out as the check.
    """
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    output_dir = output_dir or data_dir.parent / "outputs"
    orders_path = data_dir / "olist_orders_dataset.csv"
    saved_risk = output_dir / "prediction_check.json"
    if not orders_path.exists() and not (output_dir / "joined_orders.csv").exists():
        if not saved_risk.exists():
            raise FileNotFoundError("The Olist order file is not in this copy of the project.")
        payload = json.loads(saved_risk.read_text(encoding="utf-8"))
        payload["factors"] = pd.DataFrame(payload["factors"])
        payload["deciles"] = pd.DataFrame(payload.get("deciles", []))
        return payload
    if orders_path.exists():
        orders = pd.read_csv(
            orders_path,
            usecols=[
                "order_id",
                "customer_id",
                "order_status",
                "order_purchase_timestamp",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
            parse_dates=[
                "order_purchase_timestamp",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
        )
        customers = pd.read_csv(
            data_dir / "olist_customers_dataset.csv",
            usecols=["customer_id", "customer_state"],
        )
    else:
        orders = None
        customers = None
        joined = pd.read_csv(
            output_dir / "joined_orders.csv",
            usecols=[
                "order_status",
                "order_purchase_timestamp",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
                "is_late",
                "promised_lead_days",
                "region",
            ],
            parse_dates=[
                "order_purchase_timestamp",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            ],
        )
        delivered = joined.loc[
            (joined["order_status"] == "delivered")
            & joined["order_delivered_customer_date"].notna()
            & joined["order_estimated_delivery_date"].notna()
        ].copy()
        delivered["is_late"] = _as_late_flag(delivered["is_late"]).astype(bool)
        delivered = delivered.loc[delivered["promised_lead_days"].between(0, 120)]
    if orders is not None:
        delivered = orders.loc[
            (orders["order_status"] == "delivered")
            & orders["order_delivered_customer_date"].notna()
            & orders["order_estimated_delivery_date"].notna()
        ].copy()
        delivered["is_late"] = (
            delivered["order_estimated_delivery_date"].dt.normalize()
            - delivered["order_delivered_customer_date"].dt.normalize()
        ).dt.days < 0
        delivered["promised_lead_days"] = (
            delivered["order_estimated_delivery_date"].dt.normalize()
            - delivered["order_purchase_timestamp"].dt.normalize()
        ).dt.days
        delivered = delivered.merge(customers, on="customer_id", how="left")
        delivered["region"] = delivered["customer_state"].map(REGION).fillna("Other")
        delivered = delivered.loc[delivered["promised_lead_days"].between(0, 120)]

    train = delivered.loc[delivered["order_purchase_timestamp"] < "2018-01-01"]
    test = delivered.loc[
        (delivered["order_purchase_timestamp"] >= "2018-01-01")
        & (delivered["order_purchase_timestamp"] < "2018-09-01")
    ]
    features = ["region", "promised_lead_days"]
    model = Pipeline([
        ("columns", ColumnTransformer([
            ("region", OneHotEncoder(categories=[REGION_ORDER], drop="first", handle_unknown="ignore"), ["region"]),
            ("promise", "passthrough", ["promised_lead_days"]),
        ])),
        ("model", LogisticRegression(max_iter=400)),
    ])
    model.fit(train[features], train["is_late"].astype(int))
    probability = model.predict_proba(test[features])[:, 1]
    test = test.copy()
    test["risk"] = probability
    test["decile"] = pd.qcut(test["risk"].rank(method="first"), 10, labels=False) + 1

    region_rate = train.groupby("region")["is_late"].mean()
    baseline = test["region"].map(region_rate).fillna(train["is_late"].mean())
    auc = float(roc_auc_score(test["is_late"].astype(int), probability))
    baseline_auc = float(roc_auc_score(test["is_late"].astype(int), baseline))

    cutoff = test["risk"].quantile(0.90)
    flagged = test.loc[test["risk"] >= cutoff]
    precision = float(flagged["is_late"].mean())
    recall = float(flagged["is_late"].sum() / test["is_late"].sum())
    test_late = float(test["is_late"].mean())

    encoder = model.named_steps["columns"].named_transformers_["region"]
    names = list(encoder.get_feature_names_out(["region"])) + ["promised_lead_days"]
    coefficients = model.named_steps["model"].coef_[0]
    factors = []
    for name, coefficient in zip(names, coefficients):
        if name == "promised_lead_days":
            label = "Each extra day promised"
        else:
            label = name.split("_", 1)[-1].replace("region_", "")
            label = f"{label} versus Southeast"
        factors.append({"factor": label, "odds": float(pow(2.718281828, coefficient))})
    factor_table = pd.DataFrame(factors).sort_values("odds", ascending=False)
    deciles = (
        test.groupby("decile", as_index=False)
        .agg(orders=("is_late", "size"), late_rate=("is_late", "mean"), mean_risk=("risk", "mean"))
        .sort_values("decile")
    )

    return {
        "train_orders": int(len(train)),
        "test_orders": int(len(test)),
        "test_late_rate": test_late,
        "auc": auc,
        "baseline_auc": baseline_auc,
        "precision": precision,
        "recall": recall,
        "lift": precision / test_late if test_late else 0.0,
        "factors": factor_table,
        "deciles": deciles,
    }
