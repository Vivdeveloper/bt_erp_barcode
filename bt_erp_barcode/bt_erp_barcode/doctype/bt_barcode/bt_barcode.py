# Copyright (c) 2026, BT ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, getdate

class BTBarcode(Document):
	def validate(self):
		used = set()
		format_str = get_barcode_format()
		for row in self.get("items") or []:
			serial = cstr(row.get("serial_number")).strip()
			barcode = cstr(row.get("barcode")).strip()
			if barcode and barcode in used and barcode != serial:
				serial = barcode
			if not serial:
				continue
			if serial in used:
				serial, _ = _next_unique_serial(
					format_str,
					row.item_code,
					self.production_plan,
					self.posting_date,
					row.idx,
					used,
				)
			row.serial_number = serial
			row.barcode = serial
			used.add(serial)


def get_production_plan_base(production_plan: str) -> str:
	"""WO26-002/1 → WO26-002; WO26-002 → WO26-002."""
	production_plan = cstr(production_plan).strip()
	if not production_plan:
		return ""
	if "/" in production_plan:
		return production_plan.split("/", 1)[0]
	return production_plan


def get_matching_production_plans(production_plan: str) -> list[str]:
	"""All submitted Production Plans for base WO26-002: WO26-002/1, /2, /1-2, etc."""
	base = get_production_plan_base(production_plan)
	if not base:
		return []

	plans = frappe.get_all(
		"Production Plan",
		filters={"name": ["like", f"{base}/%"], "docstatus": 1},
		pluck="name",
		order_by="name asc",
	)
	# Include base WO only when it is a submitted Production Plan
	if frappe.db.exists("Production Plan", {"name": base, "docstatus": 1}):
		plans.insert(0, base)

	return sorted(set(plans))


SERIAL_NUMBER_PAD = 2


def get_barcode_format():
	"""Format from BT Barcode Settings (see placeholder reference on BT Barcode Settings)."""
	settings = frappe.get_single("BT Barcode Settings")
	format_str = (settings.get("barcode_dyamic_format") or "").strip()
	if not format_str:
		return "{MM}{YY}{production_plan}{count}"
	return format_str


def _serial_format_replacements(posting_date, production_plan: str, item_code: str, idx: int) -> dict:
	"""Placeholder values for barcode_dyamic_format (longest tokens replaced first)."""
	posting = getdate(posting_date) if posting_date else getdate()
	base_plan = get_production_plan_base(production_plan)
	row_idx = int(idx or 1)
	yy = f"{posting.year % 100:02d}"
	mm = f"{posting.month:02d}"
	count = str(row_idx).zfill(SERIAL_NUMBER_PAD)

	return {
		"{YYYY}": str(posting.year),
		"{YY}": yy,
		"{MM}": mm,
		"{production_plan}": base_plan or cstr(production_plan).strip(),
		"{count}": count,
		"{item_code}": item_code or "",
		"{idx}": str(row_idx),
		# Legacy aliases
		"{serial_number}": count,
		"{year}": str(posting.year),
		"{month}": mm,
	}


def _apply_serial_format(format_str: str, replacements: dict) -> str:
	result = format_str
	for placeholder in sorted(replacements.keys(), key=len, reverse=True):
		result = result.replace(placeholder, replacements[placeholder])
	return result


def _is_resolved_serial(serial: str) -> bool:
	"""True when serial is set and not an unresolved template."""
	serial = cstr(serial).strip()
	return bool(serial) and "{" not in serial and "}" not in serial


def generate_serial_number(
	format_str: str,
	item_code: str,
	production_plan: str,
	posting_date,
	idx: int,
) -> str:
	"""Build serial from BT Barcode Settings. {count} = row idx padded (01, 02, …)."""
	replacements = _serial_format_replacements(posting_date, production_plan, item_code or "", idx)
	return _apply_serial_format(format_str, replacements)


def _next_unique_serial(
	format_str: str,
	item_code: str,
	production_plan: str,
	posting_date,
	preferred_idx: int,
	used_serials: set,
) -> tuple[str, int]:
	"""Return unique serial; bump idx until not in used_serials."""
	idx = int(preferred_idx or 1)
	for _ in range(10000):
		serial = generate_serial_number(format_str, item_code, production_plan, posting_date, idx)
		if serial not in used_serials:
			used_serials.add(serial)
			return serial, idx
		idx += 1
	frappe.throw(_("Could not generate a unique serial number."))


def _get_items_for_single_production_plan(plan_name: str) -> list[dict]:
	"""Items from one Production Plan (serial_number left blank for manual entry)."""
	rows = frappe.get_all(
		"Production Plan Item",
		filters={"parent": plan_name, "parenttype": "Production Plan"},
		fields=["item_code", "planned_qty", "stock_uom"],
		order_by="idx",
	)
	if not rows:
		return []

	sales_order = frappe.db.get_value(
		"Sales Order", {"custom_work_order_no": plan_name}, "name"
	)
	customer = (
		frappe.db.get_value("Sales Order", sales_order, "customer") if sales_order else None
	)

	result = []
	for row in rows:
		item_name = (
			frappe.db.get_value("Item", row.item_code, "item_name") if row.item_code else ""
		)
		item_customer = None
		if row.item_code and customer:
			item_customer = frappe.db.get_value(
				"Item Customer Detail",
				{"parent": row.item_code, "customer_name": customer},
				"ref_code",
			)
		qty = max(1, int(flt(row.planned_qty)))
		for _ in range(qty):
			result.append({
				"item_code": row.item_code,
				"customer_ref_code": item_customer,
				"item_name": item_name,
				"qty": 1,
				"uom": row.stock_uom,
				"serial_number": "",
				"production_plan": plan_name,
			})
	return result


@frappe.whitelist()
def resolve_production_plan_data(production_plan: str, posting_date: str | None = None):
	"""Resolve base WO (e.g. WO26-002), matching plans, and all items."""
	base = get_production_plan_base(production_plan)
	plans = get_matching_production_plans(base)
	if not plans:
		return {"base": base, "plans": [], "items": [], "sales_order": None}

	items = []
	for plan_name in plans:
		items.extend(_get_items_for_single_production_plan(plan_name))

	return {
		"base": base,
		"plans": plans,
		"items": items,
		"sales_order": get_sales_order_for_plans(base, plans),
	}


@frappe.whitelist()
def get_items_from_production_plan(production_plan: str, posting_date: str | None = None):
	"""Fetch items from all Production Plans under base (WO26-002 → WO26-002/1, /2, …)."""
	data = resolve_production_plan_data(production_plan, posting_date)
	return data.get("items") or []


def get_sales_order_for_plans(base: str, plans: list[str] | None = None) -> str | None:
	"""Sales Order linked via custom_work_order_no on base or any matching plan."""
	for name in [base, *(plans or [])]:
		if not name:
			continue
		so = frappe.db.get_value("Sales Order", {"custom_work_order_no": name}, "name")
		if so:
			return so
	return None


def _parse_existing_serials(existing_serials) -> set:
	used = set()
	if not existing_serials:
		return used
	if isinstance(existing_serials, str):
		existing_serials = frappe.parse_json(existing_serials)
	for serial in existing_serials or []:
		if _is_resolved_serial(serial):
			used.add(cstr(serial).strip())
	return used


@frappe.whitelist()
def generate_serial_number_for_row(
	item_code=None,
	idx=None,
	production_plan=None,
	posting_date=None,
	existing_serials=None,
):
	"""Always assign next unique serial for this row idx (01, 02, 03, …)."""
	used = _parse_existing_serials(existing_serials)
	format_str = get_barcode_format()
	serial, _ = _next_unique_serial(
		format_str,
		item_code or "",
		production_plan or "",
		posting_date,
		cint(idx) or 1,
		used,
	)
	return serial


@frappe.whitelist()
def generate_serial_numbers_for_items(items, production_plan: str = "", posting_date: str | None = None):
	"""Generate serials in table order. {serial_number} = row idx (01, 02, …); fix duplicates."""
	if not items:
		return []

	if isinstance(items, str):
		items = frappe.parse_json(items)

	def get_idx(row):
		if isinstance(row, dict):
			return int(row.get("idx") or 0)
		return int(getattr(row, "idx", 0) or 0)

	items = sorted(items, key=get_idx)
	format_str = get_barcode_format()
	used_serials = set()
	result = []

	for position, row in enumerate(items, start=1):
		item_code = row.get("item_code") if isinstance(row, dict) else getattr(row, "item_code", "")
		existing = row.get("serial_number") if isinstance(row, dict) else getattr(row, "serial_number", "")
		row_idx = get_idx(row) or position

		if _is_resolved_serial(existing):
			existing = cstr(existing).strip()
			if existing not in used_serials:
				used_serials.add(existing)
				result.append(existing)
				continue

		serial, _ = _next_unique_serial(
			format_str,
			item_code or "",
			production_plan,
			posting_date,
			row_idx,
			used_serials,
		)
		result.append(serial)

	return result

@frappe.whitelist()
def generate_barcode(
	production_plan=None,
	posting_date=None,
	idx=None,
	item_code=None,
	existing_serials=None,
):
	"""Row Generate Barcode button."""
	return generate_serial_number_for_row(
		item_code=item_code,
		idx=idx,
		production_plan=production_plan,
		posting_date=posting_date,
		existing_serials=existing_serials,
	)

@frappe.whitelist()
def get_so(production_plan):
	base = get_production_plan_base(production_plan)
	plans = get_matching_production_plans(base)
	return get_sales_order_for_plans(base, plans)
	
# @frappe.whitelist()
# def get_cust_id(sales_order):
# 	cust = frappe.db.get_value("Sales Order", sales_order, 'customer')
# 	if cust:
# 		return cust