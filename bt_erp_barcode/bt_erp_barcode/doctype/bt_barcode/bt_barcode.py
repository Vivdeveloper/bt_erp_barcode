# Copyright (c) 2026, BT ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate
from frappe.model.naming import make_autoname
from datetime import datetime

class BTBarcode(Document):
	pass


def get_barcode_format():
	"""Get format from BT Barcode Settings. Supports: {item_code}, {production_plan}, {year}, {idx}"""
	settings = frappe.get_single("BT Barcode Settings")
	format_str = (settings.get("barcode_dyamic_format") or "").strip()
	if not format_str:
		return "{item_code}-{production_plan}-{year}-{idx}"
	return format_str


def generate_serial_number(format_str: str, item_code: str, production_plan: str, posting_date, idx: int) -> str:
	"""Generate serial number from format template."""
	year = str(getdate(posting_date).year) if posting_date else str(getdate().year)
	replacements = {
		"{item_code}": item_code or "",
		"{production_plan}": production_plan or "",
		"{year}": year,
		"{idx}": str(idx),
	}
	result = format_str
	for placeholder, value in replacements.items():
		result = result.replace(placeholder, value)
	return result


@frappe.whitelist()
def get_items_from_production_plan(production_plan: str, posting_date: str | None = None):
	"""Fetch items from Production Plan po_items for BT Barcode.
	Expands each item into separate rows as per qty (one row per unit for barcode printing).
	Generates serial_number per row using BT Barcode Settings format.
	"""
	if not production_plan:
		return []

	items = frappe.get_all(
		"Production Plan Item",
		filters={"parent": production_plan, "parenttype": "Production Plan"},
		fields=["item_code", "planned_qty", "stock_uom", "sales_order"],
		order_by="idx",
	)

	format_str = get_barcode_format()
	result = []
	idx = 1
	for row in items:
		item_name = frappe.db.get_value("Item", row.item_code, "item_name") if row.item_code else ""
		qty = max(1, int(flt(row.planned_qty)))
		for _ in range(qty):
			serial_number = generate_serial_number(
				format_str, row.item_code, production_plan, posting_date, idx
			)
			result.append({
				"item_code": row.item_code,
				"item_name": item_name,
				"qty": 1,
				"uom": row.stock_uom,
				"serial_number": serial_number,
			})
			idx += 1
	return result


@frappe.whitelist()
def generate_serial_number_for_row(item_code: str, idx: int, production_plan: str = "", posting_date: str | None = None):
	"""Generate serial number for a single BT Barcode Item row."""
	format_str = get_barcode_format()
	return generate_serial_number(format_str, item_code or "", production_plan, posting_date, idx or 1)


@frappe.whitelist()
def generate_serial_numbers_for_items(items, production_plan: str = "", posting_date: str | None = None):
	"""Generate serial numbers for BT Barcode Item rows using BT Barcode Settings format.
	Placeholders: {item_code}, {production_plan}, {year}, {idx}
	"""
	if not items:
		return []

	if isinstance(items, str):
		items = frappe.parse_json(items)

	# Sort by idx to maintain table order
	def get_idx(row):
		if isinstance(row, dict):
			return row.get("idx") or 0
		return getattr(row, "idx", 0) or 0

	items = sorted(items, key=get_idx)

	format_str = get_barcode_format()
	result = []
	for idx, row in enumerate(items, start=1):
		item_code = row.get("item_code") if isinstance(row, dict) else getattr(row, "item_code", "")
		serial_number = generate_serial_number(
			format_str, item_code, production_plan, posting_date, idx
		)
		result.append(serial_number)
	return result

@frappe.whitelist()
def generate_barcode(production_plan, posting_date):

    # 1. Month & Year from posting_date
    date_obj = datetime.strptime(posting_date, "%Y-%m-%d")
    month = date_obj.strftime("%m")
    year = date_obj.strftime("%y")

    # 2. Extract WO digits
    wo_digits = ''.join(filter(str.isdigit, production_plan or ""))[-4:].zfill(4)

    # 3. Prefix
    prefix = f"{month}{year}{wo_digits}"

    # 4. Generate series using prefix
    serial = make_autoname(prefix + ".####")

    return serial