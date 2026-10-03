# Veridi Logistics Delivery Performance Audit

Public dashboard, notebook, and slides for the Last Mile delivery audit.

## Executive summary

Of 96,470 delivered orders, 6.8% missed the promised date and 3.9% were more than five days late. The median order still arrived 12 days early, so the failure is a slow tail, not the typical shipment. That tail is regional: the Northeast late rate is 12.7% against 6.1% in the Southeast, with Alagoas at 21.4% and Rio de Janeiro at 12.1% on 12,350 orders, while São Paulo is 4.5% on 40,494. Review scores track the miss directly: 4.29 on time, 2.99 when one to five days late, and 1.74 when super late. The Northeast was promised 31 days for a trip that takes 20, leaving the same 11-day cushion as the Southeast, where the trip takes 11 days. The North, given a 16-day cushion, misses less often (8.6%) despite a longer road, so the date shown to the customer is the lever.

## Project links

**Notebook**

https://github.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/blob/main/data-engineering/Logistics-auditor/logistics_auditor.ipynb

**Notebook HTML export**

https://htmlpreview.github.io/?https://raw.githubusercontent.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/main/data-engineering/Logistics-auditor/logistics_auditor.html

**Dashboard**

https://amalitech-deg-project-based-challenges-3xxwauhctlmcjg4iithlir.streamlit.app/

**Presentation**

https://github.com/danmunyaneza01/AmaliTech-DEG-Project-based-challenges/raw/refs/heads/main/data-engineering/Logistics-auditor/veridi_delivery_audit.pdf

No video. The repository is public. The pages read the small summary tables in `outputs/`. The raw Olist files, and the order-level joined table built from them, are not in this repository.

## Technical notes

**Data cleaning.** Orders, customers, and reviews are joined into one row per order. Reviews are not one-to-one: 547 orders had more than one review, so those rows were collapsed to a single `order_id` (mean score) before the join. Customers join on `customer_id` with a one-to-one check. The master table stays 99,441 rows, the same length as the orders table. `Days_Difference` is the promised calendar date minus the actual delivery calendar date. Orders that are canceled, unavailable, or missing a delivery date (2,971) are flagged **Not Delivered** and kept out of the late-rate denominator. Product categories stay on a separate item table, because one order can contain several products. Each order is labeled with the English category of its highest-priced item, using `product_category_name_translation.csv`. Category rates use categories with at least 200 delivered orders. Paths are relative (`data/` and `outputs/` next to the notebook).

**Candidate's choice.** Late rate by state says where the promise was missed. It does not say whether the carrier was slow or the estimated date was too short. For each region the notebook compares promised lead time (purchase to estimated delivery) with actual lead time (purchase to delivery). The Northeast's longer promise only matched its longer trip, so the safety margin stayed about 11 days, the same as the Southeast, while the miss rate doubled. That is the feature a logistics manager can act on: widen the ETA for the Northeast and for Rio de Janeiro, where a broken date is what pulls the review score down.
