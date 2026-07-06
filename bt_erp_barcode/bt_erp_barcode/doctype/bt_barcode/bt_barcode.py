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
	"""Draft and submitted Production Plans for base WO26-002: WO26-002/1, /2, /1-2, etc."""
	base = get_production_plan_base(production_plan)
	if not base:
		return []

	docstatus_filter = ["in", [0, 1]]
	plans = frappe.get_all(
		"Production Plan",
		filters={"name": ["like", f"{base}/%"], "docstatus": docstatus_filter},
		pluck="name",
		order_by="name asc",
	)
	if frappe.db.exists("Production Plan", {"name": base, "docstatus": docstatus_filter}):
		plans.insert(0, base)

	return sorted(set(plans))


def get_work_orders_for_order_acceptance(production_plan: str) -> list[str]:
	"""Base work order and related Production Plan names (WO26-021 → WO26-021, WO26-021/1, …)."""
	base = get_production_plan_base(production_plan)
	if not base:
		return []
	return list(dict.fromkeys([base, *get_matching_production_plans(base)]))


def _sales_order_item_wo_fieldnames() -> list[str]:
	"""WO fields on Order Acceptance items: custom_wo (Data) and legacy custom_work_order."""
	meta = frappe.get_meta("Sales Order Item")
	fields: list[str] = []
	if meta.has_field("custom_wo"):
		fields.append("custom_wo")
	if meta.has_field("custom_work_order"):
		fields.append("custom_work_order")
	elif frappe.db.has_column("Sales Order Item", "custom_work_order"):
		fields.append("custom_work_order")
	return fields


def get_order_acceptances_for_work_orders(work_orders: list[str]) -> list[str]:
	"""Order Acceptance (Sales Order) names linked via items table WO field."""
	work_orders = [w for w in (work_orders or []) if w]
	if not work_orders:
		return []

	names: set[str] = set()
	for fieldname in _sales_order_item_wo_fieldnames():
		for parent in frappe.get_all(
			"Sales Order Item",
			filters={fieldname: ["in", work_orders]},
			pluck="parent",
		):
			if parent and cstr(parent).startswith("OA-"):
				names.add(parent)

	return sorted(names)


@frappe.whitelist()
def get_order_acceptances_for_production_plan(production_plan: str):
	"""Order Acceptance names whose item rows have WO matching the selected work order."""
	work_orders = get_work_orders_for_order_acceptance(production_plan)
	return get_order_acceptances_for_work_orders(work_orders)


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


ORDER_ACCEPTANCE_DOCTYPE = "Order Acceptance"
ORDER_ACCEPTANCE_ITEM_DOCTYPE = "Order Acceptance Item"
# Order Acceptance in UI is Sales Order (OA-xxx/A naming) on this site.
ORDER_ACCEPTANCE_SALES_ORDER_DOCTYPE = "Sales Order"


def _resolve_order_acceptance_doctype(name: str) -> str | None:
	"""Order Acceptance documents are Sales Order (OA-…) or custom Order Acceptance."""
	name = cstr(name).strip()
	if not name:
		return None
	if frappe.db.exists("DocType", ORDER_ACCEPTANCE_DOCTYPE) and frappe.db.exists(
		ORDER_ACCEPTANCE_DOCTYPE, name
	):
		return ORDER_ACCEPTANCE_DOCTYPE
	if frappe.db.exists(ORDER_ACCEPTANCE_SALES_ORDER_DOCTYPE, name):
		return ORDER_ACCEPTANCE_SALES_ORDER_DOCTYPE
	return None


def _child_table_has_item_fields(child_meta) -> bool:
	for fieldname in ("item_code", "item"):
		if child_meta.get_field(fieldname):
			return True
	item_name_field = child_meta.get_field("item_name")
	if not item_name_field:
		return False
	if item_name_field.fieldtype == "Link" and item_name_field.options == "Item":
		return True
	return item_name_field.fieldtype in ("Data", "Small Text", "Text", "Text Editor")


def _find_order_acceptance_items_table(meta) -> str | None:
	"""Resolve Order Acceptance line-items table (usually `items`)."""
	if meta.has_field("items"):
		child_meta = frappe.get_meta(meta.get_field("items").options)
		if _child_table_has_item_fields(child_meta):
			return "items"

	for field in meta.get_table_fields():
		child_meta = frappe.get_meta(field.options)
		if _child_table_has_item_fields(child_meta):
			return field.fieldname
	return None


def _resolve_item_code_from_row(row) -> str | None:
	"""Map OA line to Item.name (handles item_code, item, or item_name-only rows)."""
	for fieldname in ("item_code", "item"):
		code = cstr(row.get(fieldname)).strip()
		if code and frappe.db.exists("Item", code):
			return code

	item_name_value = cstr(row.get("item_name")).strip()
	if not item_name_value:
		return None
	if frappe.db.exists("Item", item_name_value):
		return item_name_value

	by_name = frappe.db.get_value("Item", {"item_name": item_name_value}, "name")
	if by_name:
		return by_name

	by_like = frappe.db.sql(
		"""
		select name from `tabItem`
		where item_name = %s or item_name like %s
		order by length(item_name) asc
		limit 1
		""",
		(item_name_value, f"{item_name_value[:80]}%"),
	)
	return by_like[0][0] if by_like else None


def _order_acceptance_row_qty(row) -> float:
	for fieldname in ("qty", "stock_qty", "work_order_qty", "planned_qty", "quantity"):
		qty = flt(row.get(fieldname))
		if qty:
			return qty
	return 1


def _order_acceptance_row_uom(row, item_code: str) -> str | None:
	uom = cstr(row.get("uom") or row.get("stock_uom")).strip()
	if uom:
		return uom
	if item_code:
		return frappe.db.get_value("Item", item_code, "stock_uom")
	return None


def _customer_for_order_acceptance(doc) -> str | None:
	for fieldname in ("customer", "custom_customer_name", "party_name"):
		customer = doc.get(fieldname)
		if customer:
			return customer
	work_order = doc.get("custom_work_order_no")
	if not work_order:
		return None
	sales_order = frappe.db.get_value(
		"Sales Order", {"custom_work_order_no": work_order}, "name"
	)
	if sales_order:
		return frappe.db.get_value("Sales Order", sales_order, "customer")
	return None


def _item_name_from_order_row(row, item_code: str) -> str:
	"""Prefer Sales Order line description over generic Item master name (e.g. Sales Item → '.')."""
	line_name = cstr(row.get("item_name")).strip()
	if line_name:
		return line_name
	if item_code:
		return cstr(frappe.db.get_value("Item", item_code, "item_name") or "").strip()
	return ""


def _customer_ref_code(item_code: str, customer: str | None, row=None) -> str | None:
	if row:
		for fieldname in ("customer_item_code", "customer_ref_code", "ref_code"):
			ref = cstr(row.get(fieldname)).strip()
			if ref:
				return ref
	if not (item_code and customer):
		return None
	return frappe.db.get_value(
		"Item Customer Detail",
		{"parent": item_code, "customer_name": customer},
		"ref_code",
	)


def _get_order_acceptance_child_rows(order_acceptance: str, table_field: str | None, child_doctype: str | None):
	if table_field and child_doctype:
		rows = frappe.get_all(
			child_doctype,
			filters={
				"parent": order_acceptance,
				"parenttype": ORDER_ACCEPTANCE_DOCTYPE,
				"parentfield": table_field,
			},
			fields=["*"],
			order_by="idx asc",
		)
		if rows:
			return rows

	if frappe.db.exists("DocType", ORDER_ACCEPTANCE_ITEM_DOCTYPE):
		return frappe.get_all(
			ORDER_ACCEPTANCE_ITEM_DOCTYPE,
			filters={
				"parent": order_acceptance,
				"parenttype": ORDER_ACCEPTANCE_DOCTYPE,
			},
			fields=["*"],
			order_by="idx asc",
		)
	return []


def _barcode_items_from_child_rows(rows, customer: str | None) -> list[dict]:
	"""Map Order Acceptance line items to BT Barcode item rows."""
	result = []
	for row in rows or []:
		row = frappe._dict(row) if isinstance(row, dict) else row
		item_code = _resolve_item_code_from_row(row)
		if not item_code:
			continue
		item_name = _item_name_from_order_row(row, item_code)
		item_customer = _customer_ref_code(item_code, customer, row)
		uom = _order_acceptance_row_uom(row, item_code)
		qty = max(1, int(flt(_order_acceptance_row_qty(row))))
		for _ in range(qty):
			result.append({
				"item_code": item_code,
				"customer_ref_code": item_customer,
				"item_name": item_name,
				"qty": 1,
				"uom": uom,
				"serial_number": "",
			})
	return result


def get_items_from_order_acceptance_doc(order_acceptance: str) -> list[dict]:
	order_acceptance = cstr(order_acceptance).strip()
	if not order_acceptance:
		return []

	doctype = _resolve_order_acceptance_doctype(order_acceptance)
	if not doctype:
		return []

	doc = frappe.get_doc(doctype, order_acceptance)

	if doctype == ORDER_ACCEPTANCE_SALES_ORDER_DOCTYPE:
		return _barcode_items_from_child_rows(doc.items, doc.get("customer"))

	table_field = _find_order_acceptance_items_table(doc.meta)
	child_doctype = doc.meta.get_field(table_field).options if table_field else None

	rows = list(doc.get(table_field) or []) if table_field else []
	if not rows:
		rows = _get_order_acceptance_child_rows(order_acceptance, table_field, child_doctype)

	customer = _customer_for_order_acceptance(doc)
	return _barcode_items_from_child_rows(rows, customer)


@frappe.whitelist()
def get_items_from_order_acceptance(order_acceptance: str, posting_date: str | None = None):
	"""Fetch Items table rows from Order Acceptance child items."""
	return get_items_from_order_acceptance_doc(order_acceptance)


@frappe.whitelist()
def get_production_plans(production_plan: str):
	"""Base work order and related Production Plan names for the production_plans child table."""
	base = get_production_plan_base(production_plan)
	return {"base": base, "plans": get_matching_production_plans(base)}


@frappe.whitelist()
def get_items_from_production_plan(production_plan: str, posting_date: str | None = None):
	"""Fetch items from all Production Plans under base (WO26-002 → WO26-002/1, /2, …)."""
	base = get_production_plan_base(production_plan)
	items = []
	for plan_name in get_matching_production_plans(base):
		items.extend(_get_items_for_single_production_plan(plan_name))
	return items


def get_sales_order_for_plans(base: str, plans: list[str] | None = None) -> str | None:
	"""First Order Acceptance linked to base or matching production plans."""
	work_orders = list(dict.fromkeys([base, *(plans or [])]))
	order_acceptances = get_order_acceptances_for_work_orders(work_orders)
	return order_acceptances[0] if order_acceptances else None


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
	
@frappe.whitelist()
def get_sales_order_item(production_plan):

    exist = frappe.db.exists("Sales Order Item", {"custom_wo": production_plan})

    records = frappe.get_all(
        "Sales Order Item",
        filters={"custom_wo": production_plan},
        fields=["name", "parent", "custom_wo"]
    )
    return records