import frappe


def execute():
	"""Force Work Order (production_plan) to Link → Production Plan without losing form logic."""
	frappe.db.sql(
		"""
		UPDATE `tabDocField`
		SET fieldtype = 'Link',
			options = 'Production Plan',
			label = 'Work Order'
		WHERE parent = 'BT Barcode' AND fieldname = 'production_plan'
		"""
	)

	# Remove Customize Form overrides that force Data / blank options
	frappe.db.sql(
		"""
		DELETE FROM `tabProperty Setter`
		WHERE doc_type = 'BT Barcode'
			AND field_name = 'production_plan'
			AND property IN ('fieldtype', 'options')
			AND value IN ('Data', '', 'None')
		"""
	)

	_ensure_property_setter(
		name="BT Barcode-production_plan-fieldtype",
		property="fieldtype",
		property_type="Select",
		value="Link",
	)
	_ensure_property_setter(
		name="BT Barcode-production_plan-options",
		property="options",
		property_type="Text",
		value="Production Plan",
	)
	_ensure_property_setter(
		name="BT Barcode-production_plan-label",
		property="label",
		property_type="Data",
		value="Work Order",
	)

	frappe.clear_cache(doctype="BT Barcode")


def _ensure_property_setter(name: str, property: str, property_type: str, value: str):
	if frappe.db.exists("Property Setter", name):
		frappe.db.set_value(
			"Property Setter",
			name,
			{"value": value, "property_type": property_type},
			update_modified=False,
		)
		return

	ps = frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocField",
			"doc_type": "BT Barcode",
			"field_name": "production_plan",
			"property": property,
			"property_type": property_type,
			"value": value,
			"name": name,
			"module": "BT ERP Barcode",
		}
	)
	ps.insert(ignore_permissions=True)
