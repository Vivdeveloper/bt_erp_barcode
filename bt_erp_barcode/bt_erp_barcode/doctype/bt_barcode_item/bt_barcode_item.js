// Copyright (c) 2026, BT ERP and contributors
// For license information, please see license.txt

frappe.ui.form.on("BT Barcode Item", {
	generate_barcode(frm, cdt, cdn) {
		if (frm.doctype !== "BT Barcode") {
			return;
		}
		bt_barcode_generate_row(frm, cdt, cdn);
	},
});
