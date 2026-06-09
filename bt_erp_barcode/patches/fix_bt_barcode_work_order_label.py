import frappe


def execute():
	"""Ensure Work Order label (fixes customized 'NA' label on production_plan or na)."""
	for field_name in ("production_plan", "na", "work_order"):
		frappe.db.sql(
			"""
			UPDATE `tabProperty Setter`
			SET value = 'Work Order'
			WHERE doc_type = 'BT Barcode'
				AND field_name = %s
				AND property = 'label'
			""",
			field_name,
		)
		frappe.db.sql(
			"""
			UPDATE `tabDocField`
			SET label = 'Work Order'
			WHERE parent = 'BT Barcode' AND fieldname = %s
			""",
			field_name,
		)

	for fieldname in ("na", "custom_na"):
		name = frappe.db.get_value(
			"Custom Field", {"dt": "BT Barcode", "fieldname": fieldname}
		)
		if name:
			frappe.db.set_value("Custom Field", name, "label", "Work Order", update_modified=False)

	if frappe.db.exists("Property Setter", "BT Barcode-production_plan-label"):
		frappe.db.set_value(
			"Property Setter",
			"BT Barcode-production_plan-label",
			"value",
			"Work Order",
			update_modified=False,
		)

	frappe.clear_cache(doctype="BT Barcode")
