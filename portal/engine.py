"""Client for the tax engine, and the shaping of its report into what the portal shows.

The browser never talks to the engine. The portal calls it server-side with the
internal key, then returns only what the signed-in person is allowed to see.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

# The engine may be asleep (free hosting). Give it time to wake before giving up.
TIMEOUT_SECONDS = 75


class EngineError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def fetch_summary(settings, shop, date_from, date_to, countries, split, filing=None):
    """filing: {country: currency its return is filed in}; countries left out use the store's currency."""
    query = urllib.parse.urlencode({
        "shop": shop, "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
        "countries": ",".join(countries), "split": ",".join(split),
        "filing": ",".join(f"{c}:{cur}" for c, cur in (filing or {}).items()),
    })
    req = urllib.request.Request(f"{settings.engine_url}/reports/summary?{query}",
                                 headers={"X-Internal-Key": settings.engine_key})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (429, 502, 503, 504):
            raise EngineError("The reporting service is starting up. Please try again in a minute.", 503)
        raise EngineError("The reporting service returned an error.")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise EngineError("The reporting service could not be reached. Please try again in a minute.", 503)


def _d(value):
    return Decimal(value or "0")


def _s(value):
    return format(value, "f")


_MONEY = ("net_sales", "tax_charged", "refunded_tax", "net_tax")


def _component(row):
    return {"title": row["title"], "rate": row["rate"],
            "taxable_sales": row["implied_taxable_sales"], "tax": row["tax_collected"]}


def _money_block(rows):
    out = {"orders": sum(r["orders"] for r in rows)}
    for key in _MONEY:
        out[key] = _s(sum((_d(r[key]) for r in rows), Decimal(0)))
    # Tax a marketplace collected and remits itself. It is part of tax_charged.
    out["marketplace_tax"] = _s(sum((_d(r.get("channel_liable_tax")) for r in rows), Decimal(0)))
    return out


def shape(summary, configured, staff):
    """Turn the engine's flat rows into one block per configured country.

    configured: [{"country": "US", "split_by_region": True, "filing_currency": "USD" or None}, ...]
    in display order. Every configured country appears, even with no sales, so an empty period
    reads as "nothing sold" and not as "missing".

    Each country is split into parts, one per currency. The part in the filing currency comes
    first. Any other part holds orders charged in a different currency, shown as charged and
    not converted. Amounts in different currencies are never added together.
    """
    store_currency = (summary.get("currencies") or [None])[0]
    components = {}
    for row in summary["by_component"]:
        components.setdefault((row["country"], row["province"], row["currency"]), []).append(_component(row))

    countries = []
    for entry in configured:
        code, split = entry["country"], entry["split_by_region"]
        filing = entry.get("filing_currency") or store_currency
        rows = [r for r in summary["by_jurisdiction"] if r["country"] == code]
        currencies = sorted({r["currency"] for r in rows} | {filing}, key=lambda c: (c != filing, c or ""))
        parts = []
        for cur in currencies:
            mine = [r for r in rows if r["currency"] == cur]
            if not mine and cur != filing:
                continue
            part = {"currency": cur, "in_filing_currency": cur == filing, **_money_block(mine)}
            if split:
                part["regions"] = [{
                    "region": r["province"], "orders": r["orders"],
                    **{key: r[key] for key in _MONEY},
                    "marketplace_tax": r.get("channel_liable_tax", "0"),
                    "components": components.get((code, r["province"], cur), []),
                } for r in mine]
            else:
                part["components"] = components.get((code, None, cur), [])
            parts.append(part)
        countries.append({"country": code, "split_by_region": split, "filing_currency": filing, "parts": parts})

    totals = [{"currency": t["currency"], "orders": t["orders"], **{key: t[key] for key in _MONEY},
               "marketplace_tax": t.get("channel_liable_tax", "0")}
              for t in summary.get("totals_by_currency") or []]
    out = {
        "period": {"date_from": summary["date_from"], "date_to": summary["date_to"],
                   "timezone": summary.get("timezone", "UTC")},
        "store_currency": store_currency,
        "totals_by_currency": totals,
        "countries": countries,
    }
    if staff:
        # Review items for the tax team. Clients never receive these.
        out["review"] = {"exceptions": summary["exceptions"],
                         "outside_selection": summary.get("outside_selection", [])}
    return out
