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
    }
