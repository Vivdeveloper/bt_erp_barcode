# Copyright (c) 2026, BT ERP and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from bt_erp_barcode.bt_erp_barcode.doctype.bt_barcode.bt_barcode import (
	SERIAL_NUMBER_PAD,
	generate_serial_number,
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
