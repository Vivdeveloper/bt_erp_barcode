# Copyright (c) 2026, BT ERP and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode import (
	SERIAL_NUMBER_PAD,
	generate_serial_number,
	get_items_from_order_acceptance_doc,
)


class TestBTBarcode(FrappeTestCase):
	def test_count_padding_two_digits(self):
		self.assertEqual(SERIAL_NUMBER_PAD, 2)

	def test_generate_serial_number_format(self):
		format_str = "{MM}{YY}{production_plan}{count}"
		serial = generate_serial_number(
			format_str,
			"ITEM-001",
			"WO26-003",
			"2026-05-18",
			1,
		)
		self.assertEqual(serial, "0526WO26-00301")

		serial2 = generate_serial_number(
			format_str,
			"ITEM-001",
			"WO26-003",
			"2026-05-18",
			2,
		)
		self.assertEqual(serial2, "0526WO26-00302")

	def test_order_acceptance_items_from_sales_order(self):
		for so_name in ("OA-001/A", "OA-003/A"):
			if frappe.db.exists("Sales Order", so_name):
				break
		else:
			self.skipTest("No OA Sales Order on this site")
		items = get_items_from_order_acceptance_doc(so_name)
		self.assertGreaterEqual(len(items), 1)
		self.assertTrue(items[0].get("item_code"))
		so_rows = frappe.get_all(
			"Sales Order Item",
			filters={"parent": so_name},
			fields=["item_code", "item_name", "customer_item_code"],
			order_by="idx asc",
			limit=1,
		)
		so_item = so_rows[0] if so_rows else None
		if so_item:
			self.assertEqual(items[0]["item_code"], so_item.item_code)
			self.assertEqual(items[0]["item_name"], so_item.item_name)
			self.assertEqual(items[0]["customer_ref_code"], so_item.customer_item_code)
